"""Animate an icon from a lit / unlit pair of stills so its light sources really light it.

An image model renders the icon twice, pixel-aligned: once with its light source on (flame
burning, fairy lights glowing) and once with it off. `lit - unlit` is then a genuine light pass:
what the source adds to every surface around it. Frames are rebuilt as

    unlit + light_pass * intensity(t)          (per light source, each with its own phase)

plus the emitter itself (warped flame sprite / bulbs), bloom that also feeds the alpha channel so
the glow survives on dark backgrounds, particles and a contact shadow. That is the same trick the
Airbnb hot-air balloon uses: the burner visibly lights the envelope.

    python3 tool/relight_icon.py campfire      fire_lit.png fire_unlit.png frames/
    python3 tool/relight_icon.py christmastree tree_lit.png tree_unlit.png frames/
    python3 tool/openlava_encode.py assets/lava/campfire frames/frame_*.png
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from animate_icon import H, SCALE, W, components, fill_holes, largest_component, yaw_rock

SS = 4
TAU = 2.0 * math.pi


# ----------------------------------------------------------------------------- helpers
def blur(a, radius):
    """Gaussian blur of a float array in [0, 255] (2D or HxWx3)."""
    if a.ndim == 3:
        return np.dstack([blur(a[..., c], radius) for c in range(a.shape[2])])
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return np.array(img.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)


def grow(mask, px):
    return np.array(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * px + 1))) > 0


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def shrink(mask, px):
    return np.array(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(2 * px + 1))) > 0


def key_backdrop(img, thr=34, matte=70.0, shadow_min=None, neutral_pockets=None, shadow_floor=None,
                 pocket_min_width=0, pocket_chroma=26, protect=None):
    """Flat-backdrop keyer (white or chroma): flood fill from the border on colour distance, soft
    matte on the outline, colours unpremultiplied against the backdrop. Returns float RGBA."""
    rgb = np.array(img.convert("RGB")).astype(np.float32)
    h, w = rgb.shape[:2]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bgcol = np.median(border, axis=0)
    dist = np.abs(rgb - bgcol).max(axis=2)
    fill = Image.fromarray((dist < thr).astype(np.uint8) * 255).copy()
    for x in range(0, w, 16):
        for seed in ((x, 0), (x, h - 1), (0, min(x, h - 1)), (w - 1, min(x, h - 1))):
            if fill.getpixel(seed) == 255:
                ImageDraw.floodfill(fill, seed, 128)
    bg = np.array(fill) == 128
    if shadow_min is not None:
        # baked drop shadow: neutral light grey hanging off the backdrop in the lower half
        # (it is smooth, so the flood stops at the textured, hard-edged stones and logs)
        mn = rgb.min(axis=2)
        gy, gx = np.gradient(blur(mn, 1.0))
        lower = (np.arange(h) > 0.45 * h)[:, None]
        cand = bg | ((rgb.max(axis=2) - mn < 24) & (mn > shadow_min) & (np.hypot(gx, gy) < 5.0) & lower)
        fill = Image.fromarray(cand.astype(np.uint8) * 255).copy()
        ys, xs = np.where(bg)
        ImageDraw.floodfill(fill, (int(xs[0]), int(ys[0])), 128)
        bg = np.array(fill) == 128
    if neutral_pockets is not None:
        # a subject with no light neutral surfaces (a dark car): whatever is pale and colourless is
        # backdrop or baked shadow showing through a gap, even where no path leads to the border
        mn = rgb.min(axis=2)
        # `pocket_chroma`: some renders tint their white backdrop and shadows (bluish here)
        pale = (rgb.max(axis=2) - mn < pocket_chroma) & (mn > neutral_pockets)
        if pocket_min_width:
            # only blobs at least this wide: thin white pinstripes on the bodywork are paint
            pale = grow(shrink(pale, pocket_min_width), pocket_min_width + 1) & pale
        if protect is not None:
            # a subject part that really is white (a helmet): box in source pixels, left alone
            px0, py0, px1, py1 = protect
            pale[py0:py1, px0:px1] = False
        bg = bg | pale
    if shadow_floor is not None:
        # baked contact shadow trapped between the wheels: below `row` (a share of the height),
        # anything colourless and lighter than the black tyres and floor is shadow on the backdrop
        # one (row, lightest[, tint]) rule, or several: the shadow gets darker towards the car
        rules = shadow_floor if isinstance(shadow_floor[0], (tuple, list)) else (shadow_floor,)
        mn = rgb.min(axis=2)
        for rule in rules:
            row, lightest = rule[:2]
            tint = rule[2] if len(rule) > 2 else 22
            below = (np.arange(h) > row * h)[:, None]
            bg = bg | ((rgb.max(axis=2) - mn < tint) & (mn > lightest) & below)
    alpha = np.where(bg, 0.0, 1.0).astype(np.float32)
    ring = grow(bg, 3) & ~bg
    a = np.clip(dist[ring] / matte, 0.0, 1.0)
    alpha[ring] = a
    keep = a > 0.06
    fixed = rgb[ring]
    fixed[keep] = np.clip((fixed[keep] - (1.0 - a[keep, None]) * bgcol) / a[keep, None], 0, 255)
    rgb[ring] = fixed
    if bgcol[1] < 90 and bgcol[0] > 180 and bgcol[2] > 180:
        # Magenta chroma key, by hue rather than by distance: nothing in the subject is magenta, a
        # shadow cast on the backdrop is just darker magenta, and enclosed pockets need no path to
        # the border. "Magenta-ness" is how far red and blue both rise above green.
        magenta = np.clip(np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1], 0, None)
        alpha = 1.0 - smoothstep(18.0, 62.0, magenta)
        # despill: what is left of the outline loses its red + blue excess over green
        rgb[..., 0] -= magenta
        rgb[..., 2] -= magenta
    alpha *= largest_component(alpha > 0.5) | (grow(largest_component(alpha > 0.5), 4) & (alpha > 0))
    return np.dstack([rgb, alpha * 255.0])


def crop_box(alpha, pad=6):
    ys, xs = np.where(alpha > 8)
    return (max(xs.min() - pad, 0), max(ys.min() - pad, 0),
            min(xs.max() + pad, alpha.shape[1] - 1), min(ys.max() + pad, alpha.shape[0] - 1))


def row_warp(rgba, shift):
    """Shift every row horizontally by shift[y] pixels (premultiplied, linear interpolation)."""
    h, w = rgba.shape[:2]
    pm = rgba.astype(np.float32).copy()
    pm[..., :3] *= pm[..., 3:4] / 255.0
    xs = np.arange(w, dtype=np.float32)
    out = np.zeros_like(pm)
    for y in range(h):
        src = xs - shift[y]
        for c in range(4):
            out[y, :, c] = np.interp(src, xs, pm[y, :, c], left=0.0, right=0.0)
    al = out[..., 3:4]
    out[..., :3] = np.where(al > 1.0, out[..., :3] / np.maximum(al / 255.0, 1e-3), 0.0)
    return out


def over(dst, src):
    """Straight-alpha float `src` over `dst` (both HxWx4, 0..255)."""
    sa, da = src[..., 3:4] / 255.0, dst[..., 3:4] / 255.0
    oa = sa + da * (1.0 - sa)
    rgb = (src[..., :3] * sa + dst[..., :3] * da * (1.0 - sa)) / np.maximum(oa, 1e-4)
    return np.dstack([rgb, oa * 255.0])


def add_glow(frame, energy, gain=1.0):
    """Additive light that also lifts alpha, so a glow is visible over any background."""
    a = frame[..., 3:4] / 255.0
    pm = frame[..., :3] * a + energy * gain
    na = np.maximum(a, np.clip(energy.max(axis=2, keepdims=True) * gain / 255.0 * 1.15, 0.0, 1.0))
    return np.dstack([np.clip(pm / np.maximum(na, 1e-4), 0, 255), na * 255.0])


# ----------------------------------------------------------------------------- subjects
class Relit:
    n_frames, fps = 48, 30
    fill, base_y = 0.84, 0.90
    width_fill = 0.94                         # widest the subject may get, as a share of the canvas
    key = dict(thr=34, matte=70.0)

    def __init__(self, lit, unlit):
        keyed = key_backdrop(unlit, **self.key)
        keyed_lit = key_backdrop(lit, **self.key)
        alpha = np.maximum(keyed[..., 3], keyed_lit[..., 3])
        x0, y0, x1, y1 = crop_box(alpha)
        scale = min(self.fill * H * SS / (y1 - y0), self.width_fill * W * SS / (x1 - x0))
        size = (int((x1 - x0) * scale), int((y1 - y0) * scale))

        def fit(a):
            return np.array(Image.fromarray(np.clip(a[y0:y1, x0:x1], 0, 255).astype(np.uint8)).resize(size, Image.LANCZOS)).astype(np.float32)

        # transparent margin so glow and bloom can spill past the silhouette
        self.margin = m = int(0.14 * max(size))
        self.at = lambda x, y: ((x - x0) * scale + m, (y - y0) * scale + m)   # source px -> layer px
        self.px = scale                                                      # source px -> layer px (lengths)
        self.unlit, self.lit = (np.pad(fit(a), ((m, m), (m, m), (0, 0))) for a in (keyed, keyed_lit))
        self.h, self.w = self.unlit.shape[:2]
        self.prepare()

    def prepare(self):
        pass

    def frame(self, t):
        """-> (float RGBA layer, yaw degrees, shadow alpha)"""
        raise NotImplementedError


class Campfire(Relit):
    key = dict(thr=34, matte=70.0, shadow_min=150)
    flame_scale = 1.30
    LIGHT_LEVELS = 8

    def prepare(self):
        lit = self.lit
        r, g, b = lit[..., 0], lit[..., 1], lit[..., 2]
        flame = (r > 205) & (g > 95) & (r - b > 85) & (lit[..., 3] > 128)
        # glowing log ends hang off the flame through thin necks: open the mask to drop them
        neck = max(2, int(0.020 * self.w))
        ys = np.where(flame.any(axis=1))[0]
        upper = np.arange(self.h)[:, None] < ys.min() + 0.45 * (ys.max() - ys.min())   # the tip is thin too
        flame = fill_holes(largest_component((grow(largest_component(shrink(flame, neck)), neck + 1) | upper) & flame))
        soft = blur(flame.astype(np.float32) * 255.0, 1.2)
        sprite = np.dstack([lit[..., :3], soft])
        ys, xs = np.where(flame)
        x0, x1, y0, y1 = xs.min() - 3, xs.max() + 4, ys.min() - 3, ys.max() + 1
        # a slightly bigger flame reads better on the tiny canvas; it grows from its base
        big = Image.fromarray(np.clip(sprite[y0:y1, x0:x1], 0, 255).astype(np.uint8))
        big = np.array(big.resize((int((x1 - x0) * self.flame_scale), int((y1 - y0) * self.flame_scale)), Image.LANCZOS)).astype(np.float32)
        self.flame = np.zeros_like(sprite)
        bx = int((x0 + x1) / 2 - big.shape[1] / 2)
        self.flame[y1 - big.shape[0]:y1, bx:bx + big.shape[1]] = big
        ys, xs = np.where(self.flame[..., 3] > 128)
        self.fy0, self.fy1, self.fcx = ys.min(), ys.max(), xs.mean()

        gain = np.clip(lit[..., :3] - self.unlit[..., :3], 0, None)
        gain *= (1.0 - blur(grow(flame, 5).astype(np.float32) * 255.0, 4) / 255.0)[..., None]
        self.light = gain * (self.unlit[..., 3:4] / 255.0)
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.radius = np.hypot(xx - self.fcx, (yy - self.fy1) * 1.6) / self.w
        self.base = np.dstack([self.unlit[..., :3], self.unlit[..., 3]])
        rng = np.random.default_rng(5)
        self.sparks = rng.uniform(0.0, 1.0, (7, 3))

    @staticmethod
    def flicker(t, ph=0.0):
        return (1.0 + 0.17 * math.sin(TAU * (3 * t + ph)) + 0.10 * math.sin(TAU * (7 * t + 1.7 * ph) + 1.3)
                + 0.05 * math.sin(TAU * (11 * t + ph)))

    def frame(self, t):
        f = self.flicker(t)
        # Tile economy: the light pass only takes LIGHT_LEVELS distinct intensities, so every tile
        # the flame does not touch repeats across the loop and is stored once per level instead of
        # once per frame (the steps are ~4 % of brightness: invisible in motion).
        level = round((f - 0.70) / 0.60 * (self.LIGHT_LEVELS - 1)) / (self.LIGHT_LEVELS - 1) * 0.60 + 0.70
        out = self.base.copy()
        out[..., :3] = np.clip(out[..., :3] + self.light * level * 1.08, 0, 255)

        # flame: rows bend more the higher they are, the whole tongue stretches and breathes
        rows = np.arange(self.h, dtype=np.float32)
        lift = np.clip((self.fy1 - rows) / max(self.fy1 - self.fy0, 1), 0.0, 1.0)
        shift = self.w * lift ** 1.7 * (0.050 * np.sin(TAU * (2 * t) + 3.2 * lift)
                                        + 0.022 * np.sin(TAU * (5 * t) + 7.0 * lift))
        flame = row_warp(self.flame, shift)
        stretch = 1.0 + 0.085 * math.sin(TAU * (4 * t)) + 0.04 * math.sin(TAU * (9 * t) + 0.8)
        fh = self.fy1 - self.fy0 + 1
        crop = Image.fromarray(np.clip(flame[self.fy0:self.fy1 + 1], 0, 255).astype(np.uint8))
        crop = np.array(crop.resize((self.w, max(2, int(fh * stretch))), Image.BICUBIC)).astype(np.float32)
        top = self.fy1 + 1 - crop.shape[0]
        layer = np.zeros_like(flame)
        layer[max(top, 0):self.fy1 + 1] = crop[max(-top, 0):]
        layer[..., :3] = np.clip(layer[..., :3] * (0.96 + 0.07 * f), 0, 255)
        out = over(out, layer)

        energy = blur(layer[..., 3], 0.030 * self.w)[..., None] * np.array([1.0, 0.52, 0.12], np.float32)
        energy += blur(layer[..., 3], 0.085 * self.w)[..., None] * np.array([0.85, 0.36, 0.06], np.float32)
        energy = np.where(energy.max(axis=2, keepdims=True) < 10.0, 0.0, energy)   # no invisible tails: they dirty far tiles
        out = add_glow(out, energy, 0.33 * f)

        dots = Image.new("L", (self.w, self.h), 0)
        draw = ImageDraw.Draw(dots)
        for s0, s1, s2 in self.sparks:
            life = (t + s0) % 1.0
            x = self.fcx + self.w * ((s1 - 0.5) * 0.20 + 0.05 * math.sin(TAU * (life * 1.5 + s2)))
            y = self.fy0 + fh * 0.35 - life * (self.fy0 + fh * 0.35) * 0.98
            rad = 0.0065 * self.w * math.sin(math.pi * life) ** 0.6
            draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=255)
        d = np.array(dots).astype(np.float32)
        spark = (d + 1.6 * blur(d, 0.012 * self.w))[..., None] * np.array([1.0, 0.72, 0.30], np.float32)
        return add_glow(out, spark, 1.0), 0.0, 0.85 + 0.15 * (2.0 - level)   # quantised like the light


class ChristmasTree(Relit):
    n_frames, fps = 60, 30
    fill, base_y = 0.90, 0.93
    key = dict(thr=60, matte=110.0)

    def prepare(self):
        body = self.unlit[..., 3:4] / 255.0
        gain = np.clip(self.lit[..., :3] - self.unlit[..., :3], 0, None) * body
        luma = gain @ np.array([0.30, 0.59, 0.11], np.float32)
        cores = luma > max(60.0, float(np.percentile(luma[body[..., 0] > 0.5], 97.5)))
        boxes = sorted(components(cores, min_px=max(6, int(2e-5 * self.w * self.h))), key=lambda b: (b[1] + b[3]))
        masks = []
        for x0, y0, x1, y1 in boxes[:40]:
            m = np.zeros((self.h, self.w), np.float32)
            m[y0:y1 + 1, x0:x1 + 1] = cores[y0:y1 + 1, x0:x1 + 1] * 255.0
            masks.append(blur(m, 0.035 * self.w) + 1e-3)
        self.star = 0
        if masks:
            total = np.sum(masks, axis=0)
            self.pools = [gain * (m / total)[..., None] * smoothstep(0.0, 6.0, total)[..., None] for m in masks]
            areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes[:40]]
            top = [i for i, b in enumerate(boxes[:40]) if b[1] < 0.22 * self.h]
            self.star = max(top, key=lambda i: areas[i]) if top else 0
        else:
            self.pools = []
        self.rest = gain - (np.sum(self.pools, axis=0) if self.pools else 0.0)
        self.base = self.unlit.copy()
        rng = np.random.default_rng(11)
        self.flakes = rng.uniform(0.0, 1.0, (7, 4))
        print(f"christmastree: {len(self.pools)} light pools (star = #{self.star})")

    # Tile economy (see Campfire.LIGHT_LEVELS): a bulb is off, half way or on - which is also how a
    # real blinker behaves - and the ambient share of the light is constant. The pseudo-3D rock makes
    # every tile of the tree unique per frame, but it is what makes the icon feel alive and it only
    # costs ~77 KB (307 -> 384 KB as AVIF), so it stays.
    BLINK_LEVELS = (0.04, 0.70, 1.30)
    ROCK_DEGREES = 9.0

    def power(self, t):
        i = np.arange(len(self.pools))
        ramp = smoothstep(-0.05, 0.35, np.sin(TAU * (2.0 * t + i * 0.29)))
        p = np.array(self.BLINK_LEVELS)[np.round(ramp * (len(self.BLINK_LEVELS) - 1)).astype(int)]
        if len(p):
            p[self.star] = (0.75, 0.90, 1.05)[int(round(1.0 + math.sin(TAU * 2 * t)))]
        return p

    def frame(self, t):
        p = self.power(t)
        light = self.rest * 0.65
        for pool, k in zip(self.pools, p):
            light = light + pool * k
        out = self.base.copy()
        out[..., :3] = np.clip(out[..., :3] + light, 0, 255)
        hot = np.clip(light - 70.0, 0, None)
        glow = blur(hot, 0.012 * self.w) * 0.9 + blur(hot, 0.04 * self.w) * 0.9
        out = add_glow(out, np.where(glow.max(axis=2, keepdims=True) < 10.0, 0.0, glow), 1.0)
        return out, self.ROCK_DEGREES * math.sin(TAU * t), 1.0

    def particles(self, canvas, t):
        cw, ch = canvas.size
        dots = Image.new("L", (cw, ch), 0)
        draw = ImageDraw.Draw(dots)
        for s0, s1, s2, s3 in self.flakes:
            life = (t + s0) % 1.0
            x = cw * (0.06 + 0.88 * s1) + 0.02 * cw * math.sin(TAU * (life + s3))
            y = ch * (-0.02 + 0.98 * life)
            rad = ch * (0.008 + 0.006 * s2) * math.sin(math.pi * life) ** 0.5
            draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=235)
        dots = dots.filter(ImageFilter.GaussianBlur(0.7 * SS * SCALE))
        flakes = Image.new("RGBA", (cw, ch), (250, 252, 255, 0))
        flakes.putalpha(dots)
        canvas.alpha_composite(flakes)


class F1Car(Relit):
    """Formula 1 car from the TV chase camera. `lit` is the still with the DRS closed, `unlit` the
    pixel-aligned edit with it open ("the upper flap has rotated flat, pivoting about its top edge:
    a thin blade at the top, and through the gap you see the engine cover ahead of the wing").

    The camera matters more than anything else here: from the front or from above the flap is a
    thin strip and an open DRS is a hairline (an image model asked to exaggerate it lifts a whole
    second wing, endplates and all). From behind, at wing height, the flap is a tall band, and
    when it lies flat the livery shows through the gap - readable at 44 px.

    The flap moves the way the mechanism does. Between the two stills, the in-between positions
    squash the closed flap against its top edge (the pivot), column by column, over the open
    still, so the gap grows from the bottom of the flap upwards.

    One story per loop: the flap opens, the car gains speed, titanium sparks pour out from under
    the diffuser towards the camera; the flap closes and they die down. The rain light blinks.

    Tile economy: two body states (a one-pixel engine vibration), four flap positions, two
    rain-light states - the car's tiles repeat; only the sparks and streaks are new per frame.
    Coordinates are in source-still pixels (1024x1024)."""

    n_frames, fps = 48, 30
    fill, base_y, width_fill = 0.74, 0.84, 0.80
    key = dict(thr=34, matte=70.0, shadow_min=150, neutral_pockets=150, shadow_floor=(0.70, 78))

    FLAP = (292, 330, 846, 470)               # columns of the flap between the endplates, rows to search
    RAIN_LIGHT = (546, 664, 602, 746)
    DIFFUSER = ((392, 836), (756, 836))       # ground line under the diffuser
    VANISHING = (512, 300)                    # where the track converges
    FLAP_STEPS = (1.0, 0.64, 0.34, 0.0)       # share of the closed flap still standing: closed .. open

    def prepare(self):
        closed, opened = self.lit, self.unlit
        x0, y0 = (int(v) for v in self.at(*self.FLAP[:2]))
        x1, y1 = (int(v) for v in self.at(*self.FLAP[2:]))
        differs = np.abs(closed - opened).max(axis=2) > 36
        changed = blur(grow(differs, max(2, int(3 * self.px))).astype(np.float32) * 255.0, 1.2 * self.px)[..., None] / 255.0

        self.states = []
        for share in self.FLAP_STEPS:
            if share == 1.0:
                self.states.append(closed)
                continue
            # everything the edit changed (endplate tips included) follows the opening...
            car = closed * (1.0 - changed) + opened * changed
            if share > 0.0:
                # ...and the part of the flap still standing is the closed flap, squashed against
                # its top edge over the open still
                for x in range(x0, x1):
                    rows = np.where(differs[y0:y1, x])[0]
                    if len(rows) < 4:
                        continue
                    top, bottom = y0 + int(rows[0]), y0 + int(rows[-1]) + 1
                    new_h = max(2, int(round((bottom - top) * share)))
                    src = np.linspace(0, bottom - top - 1, new_h)
                    band = closed[top:bottom, x]
                    car[top:top + new_h, x] = np.stack(
                        [np.interp(src, np.arange(bottom - top), band[:, c]) for c in range(4)], axis=1)
            self.states.append(car)

        lx0, ly0 = (int(v) for v in self.at(*self.RAIN_LIGHT[:2]))
        lx1, ly1 = (int(v) for v in self.at(*self.RAIN_LIGHT[2:]))
        lamp = np.zeros((self.h, self.w), np.float32)
        lamp[ly0:ly1, lx0:lx1] = 255.0
        red = (closed[..., 0] > 150) & (closed[..., 1] < 120)
        self.lamp = blur(lamp * red, 1.5 * self.px)[..., None] / 255.0

        rng = np.random.default_rng(19)
        self.sparks = rng.uniform(0.0, 1.0, (46, 5))
        self.streaks = rng.uniform(0.0, 1.0, (10, 3))

    def drs(self, i):
        """Index into `states` for frame i: the flap snaps through the in-between positions, one
        frame each, and stays open for half of the loop."""
        n, last = self.n_frames, len(self.FLAP_STEPS) - 1
        open_at, close_at = int(n * 0.22), int(n * 0.74)
        if open_at <= i < close_at:
            return min(last, i - open_at + 1)
        if i >= close_at:
            return max(0, last - (i - close_at + 1))
        return 0

    def frame(self, t):
        i = int(round(t * self.n_frames)) % self.n_frames
        state = self.drs(i)
        drs = state / (len(self.FLAP_STEPS) - 1)           # 0 closed .. 1 open
        car = self.states[state].copy()

        lamp_on = (i // 6) % 2 == 0                        # rain light: four flashes per loop
        car[..., :3] = car[..., :3] * (1.0 - self.lamp * (0.0 if lamp_on else 0.62))
        if (i // 2) % 2:                                   # engine vibration: two body states
            car = np.roll(car, int(round(0.8 * SS * SCALE)), axis=0)

        # the track rushing away: streaks along rays from the vanishing point, under the car
        vx, vy = self.at(*self.VANISHING)
        under = Image.new("L", (self.w, self.h), 0)
        draw = ImageDraw.Draw(under)
        for s0, s1, s2 in self.streaks:
            life = (t * 2.0 + s0) % 1.0                    # two passes per loop
            side = -1.0 if s1 < 0.5 else 1.0
            ray = np.array([side * (0.62 + 0.55 * s2), 1.0])
            ray /= np.linalg.norm(ray)
            near = self.px * (360 + 560 * life ** 1.6)     # accelerates towards the camera
            head = np.array([vx, vy]) + ray * near
            tail = np.array([vx, vy]) + ray * (near - self.px * (40 + 150 * life))
            fade = math.sin(math.pi * life) ** 0.7
            draw.line([tuple(tail), tuple(head)], fill=int(165 * fade), width=max(2, int(0.004 * self.w * (0.6 + life))))
        streaks = np.array(under.filter(ImageFilter.GaussianBlur(0.004 * self.w))).astype(np.float32)
        out = over(np.dstack([np.full((self.h, self.w, 3), 235.0, np.float32), streaks * 0.5]), car)

        # Titanium sparks: struck by the skid block, they leave from under the diffuser and fly
        # towards the camera, fanning out and hopping as they cool. In front of the car.
        speed = 0.28 + 0.72 * drs                          # flat out with the flap open
        hot = Image.new("RGB", (self.w, self.h), (0, 0, 0))
        draw = ImageDraw.Draw(hot)
        (dx0, dy0), (dx1, _) = self.DIFFUSER
        for s0, s1, s2, s3, s4 in self.sparks:
            if s4 > speed:                                 # fewer sparks when the car is slower
                continue
            life = (t * 3.0 + s0) % 1.0                    # three bursts per loop
            ox, oy = self.at(dx0 + (dx1 - dx0) * s1, dy0)
            ray = np.array([ox - vx, oy - vy])
            ray /= np.linalg.norm(ray)
            ray[0] += (s3 - 0.5) * 0.9                     # fan out sideways
            reach = self.px * (150 + 240 * s2) * (0.7 + 0.3 * drs)
            pos = np.array([ox, oy]) + ray * reach * life
            pos[1] -= self.px * 54 * abs(math.sin(math.pi * life * (1.4 + s3))) * (1.0 - life)
            tail = pos - ray / np.linalg.norm(ray) * self.px * (30 * (1.0 - life) + 8) * (0.7 + life)
            heat = (1.0 - life) ** 1.3 * min(1.0, life * 10.0)
            colour = (255, int(120 + 135 * heat), int(30 + 190 * heat ** 2))
            draw.line([tuple(tail), tuple(pos)], fill=tuple(int(c * (0.35 + 0.65 * heat)) for c in colour),
                      width=max(2, int(0.0034 * self.w * (0.6 + 0.8 * heat) * (0.8 + 0.6 * life))))
        hot = np.array(hot).astype(np.float32)
        glow = hot + 1.4 * blur(hot, 0.008 * self.w) + 0.8 * blur(hot, 0.03 * self.w)
        if lamp_on:
            halo = self.lamp * np.array([255.0, 40.0, 30.0], np.float32)
            glow = glow + 0.9 * blur(halo, 0.012 * self.w) + 0.6 * blur(halo, 0.04 * self.w)
        glow = np.where(glow.max(axis=2, keepdims=True) < 10.0, 0.0, glow)
        return add_glow(out, glow, 1.0), 0.0, 1.0


class F1Front(Relit):
    """Formula 1 car head-on with the driver in the cockpit; the only thing that moves is the
    steering, and it is geometry, not a second still (an image model asked to steer the wheels
    invents rims, sidewall lines and new brake ducts, and gives a different angle each time).

    The tyres are steered with light only (see `steered`): their outline stays where it is, the
    highlight of the tread slides towards the steer and the far side darkens. Warping the
    silhouette was tried and dropped - a front tyre is partly covered by the brake-duct fairing
    and the wing endplate, and the warped edge never stays in register with them.

    Ask for the still on a magenta backdrop (the helmet is white) with "plain smooth matte black
    slicks: no rim visible, no lettering, no white lines" and a helmet "small compared with the
    car, about one eighth of its width, sitting low behind the halo" - image models draw toy
    drivers with huge heads otherwise.

    Five distinct frames in the whole loop (straight, half and full lock each way): the diff atlas
    holds a handful of wheel tiles and the bundle is tiny."""

    n_frames, fps = 72, 24                     # a slow three-second weave
    fill, base_y, width_fill = 0.86, 0.93, 0.88
    key = dict(thr=60, matte=110.0)

    TYRES = ((40, 500, 245, 850), (779, 500, 984, 850))    # front tyre boxes in source pixels
    SLIDE = 0.13                               # how far the tread highlight travels, in tyre widths
    SHADE = 0.30                               # how much the far side of the tread darkens
    #          start  straight->left   hold left   back       straight    ->right     hold right  back
    TIMELINE = ((0.00, 0), (0.12, 1), (0.16, 2), (0.38, 1), (0.42, 0), (0.62, 3), (0.66, 4), (0.88, 3), (0.92, 0))

    def prepare(self):
        car = self.lit
        rgb, alpha = car[..., :3], car[..., 3]
        rubber = (rgb.max(axis=2) < 105) & (rgb.max(axis=2) - rgb.min(axis=2) < 26) & (alpha > 200)
        self.tyres = []
        for x0, y0, x1, y1 in self.TYRES:
            (ax, ay), (bx, by) = self.at(x0, y0), self.at(x1, y1)
            box = np.zeros((self.h, self.w), bool)
            box[int(ay):int(by), int(ax):int(bx)] = True
            mask = fill_holes(largest_component(rubber & box)) & box
            ys, xs = np.where(mask)
            self.tyres.append((mask, xs.min(), xs.max() + 1, ys.min(), ys.max() + 1))
        self.states = [car] + [self.steered(d * a) for d in (-1.0, 1.0) for a in (0.5, 1.0)]

    def steered(self, amount):
        """The car with both front tyres steered by `amount` of full lock (< 0: to the left).

        The outline of the tyres does not move. A front tyre is partly covered by the brake-duct
        fairing and the wing endplate, and any warp of its silhouette drifts out of register with
        what covers it. What the eye reads as a wheel turning a few degrees is the light on the
        tread: the soft highlight slides towards the steer and the far side falls into shade. So
        only the colour inside the tyre mask changes - alpha is untouched, nothing can tear."""
        car = self.lit
        out = car.copy()
        for mask, x0, x1, y0, y1 in self.tyres:
            width = x1 - x0
            slide = self.SLIDE * width * amount
            cols = np.arange(width, dtype=np.float32)
            span = cols / max(1.0, width - 1)
            away = span if amount < 0 else 1.0 - span
            shade = 1.0 - self.SHADE * abs(amount) * smoothstep(0.30, 1.0, away)
            for row in range(y0, y1):
                inside = np.where(mask[row, x0:x1])[0]
                if len(inside) < 4:
                    continue
                lo, hi = inside[0], inside[-1]
                src = np.clip(cols[lo:hi + 1] - slide, lo, hi)            # sample inside this row of rubber
                for c in range(3):
                    moved = np.interp(src, cols, car[row, x0:x1, c]) * shade[lo:hi + 1]
                    keep = mask[row, x0 + lo:x0 + hi + 1]
                    out[row, x0 + lo:x0 + hi + 1, c] = np.where(keep, moved, out[row, x0 + lo:x0 + hi + 1, c])
        return out

    def frame(self, t):
        state = 0
        for start, index in self.TIMELINE:
            if t >= start:
                state = index
        return self.states[state], 0.0, 1.0


def brazil_flag(width=840, mirrored=False):
    """The Brazilian flag as a texture (20:14): green field, yellow rhombus, blue disc, white band
    and a scatter of stars. The motto is left out - it is not legible at icon size."""
    w, h = width, int(width * 0.7)
    img = Image.new("RGB", (w, h), (0, 146, 62))            # a touch deeper than the spec green: it renders neon otherwise
    draw = ImageDraw.Draw(img)
    m = 0.085 * w                                           # rhombus margin (1.7 of 20 modules)
    draw.polygon([(m, h / 2), (w / 2, m), (w - m, h / 2), (w / 2, h - m)], fill=(255, 223, 0))
    r = 0.175 * w                                           # disc radius (3.5 modules)
    cx, cy = w / 2, h / 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 39, 118))
    # the white band: part of a big circle centred below and to the left, clipped to the disc
    band = Image.new("L", (w, h), 0)
    bd = ImageDraw.Draw(band)
    bx, by, br = cx - 0.10 * w, cy + 0.42 * w, 0.47 * w
    bd.ellipse([bx - br, by - br, bx + br, by + br], fill=255)
    inner = br - 0.030 * w
    bd.ellipse([bx - inner, by - inner, bx + inner, by + inner], fill=0)
    disc = Image.new("L", (w, h), 0)
    ImageDraw.Draw(disc).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    img.paste((255, 255, 255), (0, 0), Image.fromarray(np.minimum(np.array(band), np.array(disc))))
    rng = np.random.default_rng(1889)
    for _ in range(14):                                     # stars, below the band
        ang, rad = rng.uniform(0.15, 2.95), r * math.sqrt(rng.uniform(0.05, 0.80))
        sx, sy = cx + rad * math.cos(ang), cy + abs(rad * math.sin(ang)) * 0.9 + 0.01 * w
        if (sx - cx) ** 2 + (sy - cy) ** 2 < (0.9 * r) ** 2:
            q = 0.006 * w
            draw.ellipse([sx - q, sy - q, sx + q, sy + q], fill=(255, 255, 255))
    return np.array(img.transpose(Image.FLIP_LEFT_RIGHT) if mirrored else img).astype(np.float32)


class SennaFlag(Relit):
    """A 1988-style red and white Formula 1 car on its victory lap, the driver holding a flagpole
    out of the cockpit. One still (pass it twice) of the car with a BARE pole - "the pole is
    completely bare: no flag, no cloth, no banner" - and the flag is cloth simulated here, so it
    loops perfectly and needs no second image.

    The flag is a mesh hanging from the top of the pole and streaming behind the car. A wave
    travels from the hoist to the fly with growing amplitude (it is pinned at the pole), a second,
    faster ripple rides on it, the fly end droops a little, and the cloth is foreshortened where
    it turns away (each strip advances by the cosine of its slope). Folds are shaded by their
    slope against a top-left light, which is what makes it read as fabric rather than a sticker.
    It is drawn UNDER the car layer: the pole and the glove stay in front.

    Coordinates are in source-still pixels (1024x1024, car pointing to the lower right)."""

    n_frames, fps = 36, 24                     # one majestic wave cycle every 1.5 s
    fill, base_y, width_fill = 0.78, 0.93, 0.92
    key = dict(thr=60, matte=110.0)

    POLE_TIP, FLAG_FOOT = (509, 176), (580, 356)            # the stretch of pole the hoist is tied to
    STREAM = (-0.965, -0.262)                               # where the fly end points (behind the car)
    LENGTH = 395.0
    GRID = (168, 100)                          # fine enough for the rhombus and disc edges to stay smooth

    def prepare(self):
        self.car = self.lit
        self.cloth = brazil_flag(mirrored=True)             # we see the reverse: the hoist is on the right

    def flag_layer(self, t):
        nu, nv = self.GRID
        u = np.linspace(0.0, 1.0, nu + 1)
        v = np.linspace(0.0, 1.0, nv + 1)
        p0, p1 = np.array(self.at(*self.POLE_TIP)), np.array(self.at(*self.FLAG_FOOT))
        d = np.array(self.STREAM) / np.linalg.norm(self.STREAM)
        up = np.array([-d[1], d[0]])
        if up[1] > 0:
            up = -up                                        # screen-up is negative y
        length = self.LENGTH * self.px

        uu, vv = np.meshgrid(u, v)                          # (nv+1, nu+1)
        amp = 52.0 * self.px * uu ** 1.15
        phase = TAU * (1.55 * uu - t) + 0.85 * vv
        wave = amp * np.sin(phase) + 0.30 * amp * np.sin(TAU * (3.2 * uu - 2.0 * t) + 1.9 * vv + 1.0)
        slope = np.gradient(wave, axis=1) / (length / nu)
        along = np.cumsum(np.cos(np.arctan(slope)) * (length / nu), axis=1)
        along = along - along[:, :1]
        droop = 34.0 * self.px * uu ** 2.0

        hoist = p0[None, None, :] + vv[..., None] * (p1 - p0)[None, None, :]
        pts = hoist + along[..., None] * d + wave[..., None] * up
        pts[..., 1] += droop

        # light from the top left: folds facing it brighten, folds turned away darken
        lit = np.clip(0.96 - 0.95 * slope, 0.48, 1.34)
        sheen = np.clip(-slope - 0.25, 0.0, 1.0) ** 2 * 60.0

        th, tw = self.cloth.shape[:2]
        layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for j in range(nv):
            ty = min(th - 1, int((j + 0.5) / nv * th))
            for i in range(nu):
                tx = min(tw - 1, int((i + 0.5) / nu * tw))
                k = 0.25 * (lit[j, i] + lit[j, i + 1] + lit[j + 1, i] + lit[j + 1, i + 1])
                g = 0.25 * (sheen[j, i] + sheen[j, i + 1] + sheen[j + 1, i] + sheen[j + 1, i + 1])
                colour = tuple(int(min(255.0, c * k + g)) for c in self.cloth[ty, tx])
                quad = [tuple(pts[j, i]), tuple(pts[j, i + 1]), tuple(pts[j + 1, i + 1]), tuple(pts[j + 1, i])]
                draw.polygon(quad, fill=colour + (255,))
        return np.array(layer).astype(np.float32)

    def frame(self, t):
        return over(self.flag_layer(t), self.car), 0.0, 1.0


SUBJECTS = {"campfire": Campfire, "christmastree": ChristmasTree, "f1car": F1Car, "f1front": F1Front, "sennamp4": SennaFlag}


def render(kind, lit, unlit, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    subj = SUBJECTS[kind](lit, unlit)
    cw, ch = W * SS, H * SS
    dx, dy = getattr(subj, "offset", (0.0, 0.0))
    cx, base = cw / 2 + dx * cw, subj.base_y * ch + dy * ch
    pad = int(0.16 * max(subj.w, subj.h))
    paths = []
    for i in range(subj.n_frames):
        t = i / subj.n_frames
        layer, yaw, shadow_alpha = subj.frame(t)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        if hasattr(subj, "shadow"):
            soft = subj.shadow((cw, ch), (cx - subj.w / 2, base - subj.h + subj.margin))
        else:
            sh = Image.new("L", (cw, ch), 0)
            body_w, body_h = subj.w - 2 * subj.margin, subj.h - 2 * subj.margin
            sw, shh = body_w * 0.44, body_h * 0.05
            ImageDraw.Draw(sh).ellipse([cx - sw, base - shh, cx + sw, base + shh], fill=int(95 * shadow_alpha))
            soft = sh.filter(ImageFilter.GaussianBlur(9 * SS * SCALE))
        canvas.paste(Image.new("RGBA", (cw, ch), (20, 16, 12, 255)), (0, 0), soft)
        big = Image.new("RGBA", (subj.w + 2 * pad, subj.h + 2 * pad), (0, 0, 0, 0))
        big.alpha_composite(Image.fromarray(np.clip(layer, 0, 255).astype(np.uint8)), (pad, pad))
        if yaw:
            big = yaw_rock(big, yaw)
        canvas.alpha_composite(big, (int(round(cx - big.width / 2)), int(round(base - pad - subj.h + subj.margin))))
        if hasattr(subj, "particles"):
            subj.particles(canvas, t)
        path = os.path.join(out_dir, f"frame_{i:03d}.png")
        canvas.resize((W, H), Image.LANCZOS).save(path)
        paths.append(path)
    print(f"{kind}: {len(paths)} frames @ {subj.fps} fps -> {out_dir}")
    return paths


if __name__ == "__main__":
    render(sys.argv[1], Image.open(sys.argv[2]), Image.open(sys.argv[3]), sys.argv[4])
