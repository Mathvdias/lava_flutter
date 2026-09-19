"""Turn a single rendered 3D icon (PNG on a white / neutral studio background) into a looping
frame sequence at the OpenLava canvas size used by the Airbnb assets (180x162 @2x).

Pipeline per subject:
  1. key_white   - flood-fill background removal from the border (keeps highlights inside the
                   object), drops the baked-in drop shadow;
  2. render      - N frames at 4x supersampling with layered motion:
       * subject-specific secondary animation (wind bend + falling leaves for the bonsai,
         screen blink / glow pulse / scanline sweep for the Macintosh),
       * a pseudo-3D yaw rock (perspective warp) + hover bob for every subject,
       * a synthetic soft contact shadow that reacts to the motion.
Usage: python3 animate_icon.py <bonsai|macintosh> <still.png> <out_dir> [n_frames]
"""
import sys, os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# OpenLava canvas: 180x162 is the Airbnb size (density 2). LAVA_SCALE=2 renders the same icon at
# 360x324 (density 4) for the large previews; every pixel-sized constant below scales with it.
SCALE = int(os.environ.get("LAVA_SCALE", "1"))
W, H = 180 * SCALE, 162 * SCALE
SS = 4                   # supersample factor


# ----------------------------------------------------------------------------- keying
def key_white(img, chroma_thr=22, bright_thr=150, halo_px=80, halo_chroma=14, halo_min=100,
              halo_mode="chroma", halo_dist=40, edge_dist=60, halo_cool=False):
    """halo_mode "chroma": near-background pixels are dropped when neutral and bright (right for
    beige / grey subjects whose colour sits close to the backdrop, e.g. the Macintosh).
    halo_mode "distance": near-background pixels are dropped when their colour is close to the
    backdrop colour, and the outline gets a matte from that colour distance (right for saturated
    subjects such as the sunflower: pale petal highlights survive, grey pockets between petals go)."""
    rgb = np.array(img.convert("RGB")).astype(np.float32)
    h, w = rgb.shape[:2]
    mn = rgb.min(axis=2)
    chroma = rgb.max(axis=2) - mn
    cand = (chroma < chroma_thr) & (mn > bright_thr)
    fill = Image.fromarray(cand.astype(np.uint8) * 255).copy()  # fromarray is read-only; floodfill needs a writable image
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (0, h // 2), (w - 1, h // 2), (w // 2, h - 1)]
    for seed in seeds:
        if fill.getpixel(seed) == 255:
            ImageDraw.floodfill(fill, seed, 128)
    bg = np.array(fill) == 128
    bgcol = np.median(rgb[bg], axis=0) if bg.any() else np.array([255.0, 255.0, 255.0])
    dist = np.abs(rgb - bgcol).max(axis=2)          # colour distance to the backdrop
    # enclosed background pockets (between leaves and stem, between petals) never touch the
    # border: any small blob that still looks like backdrop is background too
    pocket = (dist < 22) & (chroma < 14) & ~bg
    pk = Image.fromarray(pocket.astype(np.uint8) * 255).copy()
    pys, pxs = np.where(pocket)
    for y, x in zip(pys[::17], pxs[::17]):
        if pk.getpixel((x, y)) != 255:
            continue
        ImageDraw.floodfill(pk, (x, y), 128)
        comp = np.array(pk) == 128
        ImageDraw.floodfill(pk, (x, y), 64)
        if comp.sum() >= 0.000005 * h * w:
            bg |= comp
    grown = np.array(Image.fromarray(bg.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * (halo_px // 2) + 1))) > 0
    if halo_mode == "distance":
        halo = grown & ~bg & (dist < halo_dist)
    else:
        halo = grown & ~bg & (chroma < halo_chroma) & (mn > halo_min)
        if halo_cool:
            # a rendered drop shadow is cool grey (blue >= red); warm beige / tan case panels are not
            halo &= rgb[..., 2] >= rgb[..., 0] - 4
    halo_soft = np.array(Image.fromarray(halo.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32) / 255
    alpha = np.ones((h, w), np.float32)
    alpha[bg] = 0.0
    alpha = alpha * (1 - halo_soft)
    if halo_mode == "distance":
        # soft outline: the render blends object and backdrop over a few pixels. Treat that band as
        # a matte (alpha = colour distance / typical object distance) and unpremultiply the colour
        # against the backdrop, otherwise the edge keeps the pale blended tint and reads as specks.
        ring = (np.array(Image.fromarray(bg.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(9))) > 0) & ~bg
        inner = (np.array(Image.fromarray(ring.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(13))) > 0) & ~ring & ~bg
        D = float(np.median(dist[inner])) if inner.any() else edge_dist
        D = max(D, 30.0)
        a = np.clip(dist[ring] / D, 0, 1)
        alpha[ring] = np.minimum(alpha[ring], a)
        keep = a > 0.05
        rgb_ring = rgb[ring]
        rgb_ring[keep] = np.clip((rgb_ring[keep] - (1 - a[keep, None]) * bgcol) / a[keep, None], 0, 255)
        rgb[ring] = rgb_ring
    else:
        ring = (np.array(Image.fromarray(bg.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))) > 0) & ~bg
        B = float(np.median(mn[bg])) if bg.any() else 255.0
        alpha[ring] = np.minimum(alpha[ring], np.clip((B - mn[ring]) / 50.0, 0, 1))
    # keep only the main connected object
    solid = Image.fromarray((alpha > 0.02).astype(np.uint8) * 255).copy()
    ys, xs = np.where(alpha > 0.5)
    cy, cx = int(np.median(ys)), int(np.median(xs))
    best = None
    for r in range(0, 400, 8):
        for (px, py) in [(cx + dx, cy + dy) for dx in (-r, 0, r) for dy in (-r, 0, r)]:
            if 0 <= px < w and 0 <= py < h and solid.getpixel((px, py)) == 255:
                best = (px, py); break
        if best: break
    if best:
        ImageDraw.floodfill(solid, best, 128)
        keep = np.array(solid) == 128
        keep = np.array(Image.fromarray(keep.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
        alpha = alpha * keep
    return np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)


def crop_to_alpha(rgba, pad=2):
    a = rgba[..., 3]
    ys, xs = np.where(a > 8)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, a.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, a.shape[1])
    return rgba[y0:y1 + 1, x0:x1 + 1]


KEY_PARAMS = {
    "bonsai": dict(chroma_thr=22, halo_px=80, halo_mode="distance", halo_dist=40),
    "sunflower": dict(chroma_thr=22, halo_px=80, halo_mode="distance", halo_dist=40),
    "macintosh": dict(chroma_thr=16, halo_px=110, halo_chroma=26, halo_min=60, halo_cool=True),
}


# ----------------------------------------------------------------------------- warps
def premul(a):
    a = a.astype(np.float32)
    al = a[..., 3:4] / 255.0
    return np.concatenate([a[..., :3] * al, a[..., 3:4]], axis=2)


def unpremul(p):
    al = p[..., 3:4]
    rgb = np.where(al > 1e-3, p[..., :3] / np.maximum(al / 255.0, 1e-3), 0)
    return np.clip(np.concatenate([rgb, al], axis=2), 0, 255).astype(np.uint8)


def row_shift(rgba, dx_rows):
    """Shift every row horizontally by dx_rows[y] (sub-pixel, bilinear, premultiplied)."""
    p = premul(rgba)
    h, w = p.shape[:2]
    xs = np.arange(w, dtype=np.float32)
    out = np.zeros_like(p)
    for y in range(h):
        d = dx_rows[y]
        if abs(d) < 1e-4:
            out[y] = p[y]; continue
        src = xs - d
        x0 = np.floor(src).astype(int)
        f = (src - x0)[:, None]
        x1 = x0 + 1
        v0 = np.where(((x0 >= 0) & (x0 < w))[:, None], p[y, np.clip(x0, 0, w - 1)], 0)
        v1 = np.where(((x1 >= 0) & (x1 < w))[:, None], p[y, np.clip(x1, 0, w - 1)], 0)
        out[y] = v0 * (1 - f) + v1 * f
    return unpremul(out)


def to_premul_image(img):
    return Image.fromarray(np.clip(premul(np.array(img)), 0, 255).astype(np.uint8))


def from_premul_image(img):
    return Image.fromarray(unpremul(np.array(img).astype(np.float32)))


def rotate_pm(img, angle, center):
    """Bicubic rotation without dark edge halos: rotate premultiplied, then unpremultiply."""
    return from_premul_image(to_premul_image(img).rotate(angle, resample=Image.BICUBIC, center=center))


def find_coeffs(out_pts, in_pts):
    m = []
    for (x, y), (u, v) in zip(out_pts, in_pts):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    A = np.array(m, float)
    b = np.array(in_pts, float).reshape(8)
    return np.linalg.lstsq(A, b, rcond=None)[0]


def yaw_rock(layer, theta_deg, k=0.05, squeeze=0.03):
    """Pseudo-3D rotation around the vertical axis: near side grows, far side shrinks."""
    lw, lh = layer.size
    s = math.sin(math.radians(theta_deg))
    sL, sR = 1 + k * s, 1 - k * s
    hw = lw / 2 * (1 - squeeze * abs(s))
    cx, cy, hh = lw / 2, lh / 2, lh / 2
    out_quad = [(cx - hw, cy - hh * sL), (cx + hw, cy - hh * sR), (cx + hw, cy + hh * sR), (cx - hw, cy + hh * sL)]
    in_quad = [(0, 0), (lw, 0), (lw, lh), (0, lh)]
    coeffs = find_coeffs(out_quad, in_quad)
    warped = to_premul_image(layer).transform((lw, lh), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    return from_premul_image(warped)


# ----------------------------------------------------------------------------- masks
def largest_component(mask):
    img = Image.fromarray(mask.astype(np.uint8) * 255).copy()
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return mask
    best, best_n = None, 0
    labelled = np.zeros(mask.shape, bool)
    for y, x in zip(ys[::37], xs[::37]):
        if labelled[y, x] or img.getpixel((x, y)) != 255:
            continue
        ImageDraw.floodfill(img, (x, y), 128)
        comp = np.array(img) == 128
        labelled |= comp
        n = comp.sum()
        if n > best_n:
            best, best_n = comp, n
        ImageDraw.floodfill(img, (x, y), 64)
    return best if best is not None else mask


def components(mask, min_px=20):
    img = Image.fromarray(mask.astype(np.uint8) * 255).copy()
    comps = []
    ys, xs = np.where(mask)
    for y, x in zip(ys, xs):
        if img.getpixel((x, y)) != 255:
            continue
        ImageDraw.floodfill(img, (x, y), 128)
        comp = np.array(img) == 128
        ImageDraw.floodfill(img, (x, y), 64)
        if comp.sum() >= min_px:
            cy, cx = np.where(comp)
            comps.append((cx.min(), cy.min(), cx.max(), cy.max()))
    return comps


def topmost_component(mask, min_px=400):
    """The connected component (>= min_px) whose centroid is highest in the image."""
    img = Image.fromarray(mask.astype(np.uint8) * 255).copy()
    ys, xs = np.where(mask)
    best, best_y = None, 1e9
    for y, x in zip(ys[::23], xs[::23]):
        if img.getpixel((x, y)) != 255:
            continue
        ImageDraw.floodfill(img, (x, y), 128)
        comp = np.array(img) == 128
        ImageDraw.floodfill(img, (x, y), 64)
        if comp.sum() >= min_px:
            cy = np.where(comp)[0].mean()
            if cy < best_y:
                best, best_y = comp, cy
    return best if best is not None else mask


def fill_holes(mask):
    """Add every enclosed hole to a binary mask (flood fill the outside, invert)."""
    h, w = mask.shape
    canvas = np.zeros((h + 2, w + 2), np.uint8)
    canvas[1:-1, 1:-1] = mask.astype(np.uint8) * 255
    img = Image.fromarray(canvas).copy()
    ImageDraw.floodfill(img, (0, 0), 128)
    outside = np.array(img) == 128
    return ~outside[1:-1, 1:-1]


# ----------------------------------------------------------------------------- subjects
class Subject:
    n_frames = 48
    fill = 0.80
    base_y = 0.86

    def __init__(self, obj):
        self.obj = obj                         # PIL RGBA, already scaled to the 4x canvas
        self.ow, self.oh = obj.size

    def layer(self, t):                        # -> PIL RGBA same size as obj (secondary animation)
        return self.obj

    def motion(self, t):                       # -> yaw_deg, dx, dy, shadow_scale, shadow_alpha
        return 0.0, 0.0, 0.0, 1.0, 1.0


class Bonsai(Subject):
    fill = 0.82

    def __init__(self, obj):
        super().__init__(obj)
        a = np.array(obj)
        r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
        foliage = (a[..., 3] > 200) & (g > r + 25) & (g > b + 25)
        ys, xs = np.where(foliage)
        self.canopy_top, self.canopy_bottom = int(np.percentile(ys, 2)), int(np.percentile(ys, 98))
        self.canopy_left, self.canopy_right = int(np.percentile(xs, 3)), int(np.percentile(xs, 97))
        med = np.median(a[foliage][:, :3], axis=0)
        self.leaf_color = tuple(int(c) for c in med)
        self.leaf_dark = tuple(max(0, int(c * 0.75)) for c in med)
        # bend profile: height above the pot rim, eased so the pot barely moves
        base = self.oh * 0.72                   # roughly where the trunk leaves the soil
        yy = np.arange(self.oh, dtype=np.float32)
        self.t_rows = np.clip((base - yy) / base, 0, 1) ** 2.2

    def layer(self, t):
        ph = 2 * math.pi * t
        amp = 0.055 * self.oh
        bend = amp * (math.sin(ph) + 0.35 * math.sin(2 * ph + 1.1))
        a = row_shift(np.array(self.obj), self.t_rows * bend)
        img = Image.fromarray(a)
        d = ImageDraw.Draw(img)
        # two leaves detaching from the canopy and tumbling down onto the pot
        for (off, x_frac, y_frac, size) in [(0.10, 0.80, 0.55, 1.0), (0.58, 0.30, 0.40, 0.8)]:
            u = (t - off) % 1.0
            if u > 0.66:
                continue
            p = (u / 0.66) ** 1.25
            x0 = self.canopy_left + (self.canopy_right - self.canopy_left) * x_frac
            y0 = self.canopy_top + (self.canopy_bottom - self.canopy_top) * y_frac
            y1 = self.oh * 0.86
            x = x0 + self.ow * 0.05 * math.sin(2 * math.pi * 1.5 * p) + self.ow * 0.04 * p + self.t_rows[int(min(self.oh - 1, y0))] * bend
            y = y0 + (y1 - y0) * p
            alpha = min(1.0, p * 10) * (1.0 if p < 0.82 else (1 - p) / 0.18)
            lw, lh = int(16 * SS / 4 * size), int(10 * SS / 4 * size)
            leaf = Image.new("RGBA", (lw * 2, lh * 2), (0, 0, 0, 0))
            ld = ImageDraw.Draw(leaf)
            ld.ellipse([lw // 2, lh // 2, lw // 2 + lw, lh // 2 + lh], fill=self.leaf_color + (int(255 * alpha),))
            ld.line([lw // 2 + 2, lh, lw // 2 + lw - 2, lh], fill=self.leaf_dark + (int(255 * alpha),), width=1)
            leaf = rotate_pm(leaf, 360 * 1.3 * p + 20, None)
            img.alpha_composite(leaf, (int(x - lw), int(y - lh)))
        return img

    def motion(self, t):
        ph = 2 * math.pi * t
        yaw = 3.5 * math.sin(ph - 0.4)
        return yaw, 0.0, 0.6 * math.sin(2 * ph), 1 + 0.03 * math.sin(ph), 1.0


class Macintosh(Subject):
    """Hovering Mac: the rendered face is erased once and a pixel face is drawn per frame so it can
    blink, glance sideways and smile; the phosphor glow pulses and a scanline band sweeps down."""
    fill = 0.86
    base_y = 0.88

    def __init__(self, obj):
        super().__init__(obj)
        a = np.array(obj).astype(int)
        r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
        screen = (al > 200) & (b > r + 12) & (g > r + 8)
        screen = largest_component(screen)
        screen = np.array(Image.fromarray(screen.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))) > 0
        self.screen = screen
        ys, xs = np.where(screen)
        self.sx0, self.sx1, self.sy0, self.sy1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        sw, sh = self.sx1 - self.sx0, self.sy1 - self.sy0
        # erase the rendered face: horizontal inpainting across the face rectangle
        base = np.array(obj)
        fx0, fx1 = self.sx0 + int(sw * 0.26), self.sx0 + int(sw * 0.74)
        fy0, fy1 = self.sy0 + int(sh * 0.30), self.sy0 + int(sh * 0.62)
        for y in range(fy0, fy1):
            l, rr = base[y, fx0 - 3:fx0, :3].mean(axis=0), base[y, fx1:fx1 + 3, :3].mean(axis=0)
            w = np.linspace(0, 1, fx1 - fx0)[:, None]
            base[y, fx0:fx1, :3] = (l * (1 - w) + rr * w).astype(np.uint8)
        blurred = Image.fromarray(base).filter(ImageFilter.GaussianBlur(2))
        patch = np.array(blurred)
        base[fy0 + 2:fy1 - 2, fx0 + 2:fx1 - 2] = patch[fy0 + 2:fy1 - 2, fx0 + 2:fx1 - 2]
        self.base = Image.fromarray(base)
        # face geometry (screen-relative)
        self.eye = int(sw * 0.115)
        self.eye_y = self.sy0 + int(sh * 0.43)
        self.eye_lx, self.eye_rx = self.sx0 + int(sw * 0.36), self.sx0 + int(sw * 0.64)
        self.mouth_y = self.sy0 + int(sh * 0.56)
        self.face_col = (240, 250, 248)
        self.soft_screen = np.array(Image.fromarray(screen.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255

    @staticmethod
    def _ease(u):
        return 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, u)))

    def _face_state(self, t):
        """(eye openness 0..1, gaze offset -1..1, smile 0..1) along the loop."""
        n = self.n_frames
        f = (t * n) % n
        # blinks: a single blink at 27% and a double blink at 68%
        openness = 1.0
        for bf in (0.27 * n, 0.68 * n, 0.68 * n + 5):
            d = f - bf
            if 0 <= d < 3:
                openness = min(openness, 0.15 if d == 1 else 0.5)
        # gaze: glance to the right after the first blink, back to centre after the double blink
        if 0.30 * n <= f < 0.40 * n:
            gaze = self._ease((f - 0.30 * n) / (0.10 * n))
        elif 0.40 * n <= f < 0.72 * n:
            gaze = 1.0
        elif 0.72 * n <= f < 0.82 * n:
            gaze = 1.0 - self._ease((f - 0.72 * n) / (0.10 * n))
        else:
            gaze = 0.0
        # smile while looking at you again
        if 0.80 * n <= f < 0.86 * n:
            smile = self._ease((f - 0.80 * n) / (0.06 * n))
        elif 0.86 * n <= f:
            smile = 1.0
        else:
            smile = 0.0
        return openness, gaze, smile

    def layer(self, t):
        openness, gaze, smile = self._face_state(t)
        img = self.base.copy()
        face = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(face)
        e = self.eye
        dx = int(gaze * e * 0.9)
        eh = max(2, int(e * openness))
        for ex in (self.eye_lx, self.eye_rx):
            x0 = ex - e // 2 + dx
            y0 = self.eye_y - eh // 2 + (e - eh) // 4
            d.rounded_rectangle([x0, y0, x0 + e, y0 + eh], radius=max(1, e // 5), fill=self.face_col + (255,))
        # mouth: flat bar that curves into a pixel smile
        mw, mh = int(e * 1.6), max(2, int(e * 0.32))
        mx = (self.eye_lx + self.eye_rx) // 2 + dx // 2
        if smile < 0.05:
            d.rounded_rectangle([mx - mw // 2, self.mouth_y, mx + mw // 2, self.mouth_y + mh], radius=mh // 2, fill=self.face_col + (255,))
        else:
            lift = int(e * 0.55 * smile)
            seg = mw // 3
            d.rounded_rectangle([mx - seg // 2, self.mouth_y + lift // 2, mx + seg // 2, self.mouth_y + lift // 2 + mh], radius=mh // 2, fill=self.face_col + (255,))
            d.rounded_rectangle([mx - mw // 2, self.mouth_y - lift // 2, mx - seg // 2 + 1, self.mouth_y - lift // 2 + mh], radius=mh // 2, fill=self.face_col + (255,))
            d.rounded_rectangle([mx + seg // 2 - 1, self.mouth_y - lift // 2, mx + mw // 2, self.mouth_y - lift // 2 + mh], radius=mh // 2, fill=self.face_col + (255,))
        glow = face.filter(ImageFilter.GaussianBlur(max(2, self.eye // 3)))
        img.alpha_composite(Image.fromarray((np.array(glow) * np.array([1, 1, 1, 0.55])).astype(np.uint8)))
        img.alpha_composite(face)
        # phosphor glow pulse + scanline sweep, confined to the screen
        a = np.array(img).astype(np.float32)
        pulse = 1 + 0.045 * math.sin(2 * math.pi * 2 * t)
        sh = self.sy1 - self.sy0
        yb = self.sy0 + sh * ((t + 0.15) % 1.0)
        yy = np.arange(self.oh, dtype=np.float32)[:, None]
        band = np.exp(-0.5 * ((yy - yb) / (0.035 * sh)) ** 2)[..., None]
        m = self.soft_screen[..., None]
        gain = (pulse + 0.07 * band) * m + (1 - m)
        a[..., :3] = np.clip(a[..., :3] * gain, 0, 255)
        return Image.fromarray(a.astype(np.uint8))

    def motion(self, t):
        ph = 2 * math.pi * t
        lift = (1 - math.cos(ph)) / 2
        yaw = 5.0 * math.sin(ph + 0.9)
        return yaw, 0.0, -4.0 * lift, 1 - 0.12 * lift, 1 - 0.35 * lift


class Sunflower(Subject):
    """Potted sunflower: the stem bends in the wind (pot stays put), the flower head turns a little
    on its own as it follows the breeze, and pollen motes drift up from the seed centre."""
    fill = 0.84
    base_y = 0.88

    def __init__(self, obj):
        super().__init__(obj)
        a = np.array(obj).astype(int)
        r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
        # petals: yellow (terracotta is excluded by the small red-green gap), centre: dark brown
        yellow = (al > 200) & (r > 175) & (g > 135) & (b < 135) & (r - g < 65)
        brown = (al > 200) & (r > 50) & (r < 165) & (g < 115) & (b < 95) & (r - g > 20)
        # merge the petals into one blob, keep the blob in the upper half (the pot is below), fill it
        closed = np.array(Image.fromarray((yellow | brown).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.MinFilter(17))) > 0
        # the pot rim: first row (from the top) where terracotta spans a good part of the object
        terracotta = (al > 200) & (r > 150) & (r - g > 55) & (g > 85) & (b < 135)
        frac = terracotta.sum(axis=1) / max(1, (al > 200).sum(axis=1).max())
        # walk up from the bottom: the pot is the contiguous terracotta band at the base
        # (petal shading can pass the colour test too, so never search from the top)
        y = self.oh - 1
        gap, tol = 0, max(3, int(0.03 * self.oh))
        while y > 0 and gap < tol:
            gap = gap + 1 if frac[y] < 0.30 else 0
            y -= 1
        self.pot_top = min(int(0.9 * self.oh), y + tol + 1) if y > 0 else int(0.55 * self.oh)
        closed[self.pot_top:, :] = False
        head = fill_holes(largest_component(closed))
        # grow generously so no petal tip is cut (a cut petal would split between the rotating and
        # the static layer), but keep the green stem / leaves out of the rotating layer
        head = np.array(Image.fromarray(head.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(int(0.05 * self.ow) | 1))) > 0
        green = (al > 200) & (g > r + 20) & (g > b + 20)
        green = np.array(Image.fromarray(green.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
        head &= ~green
        # the brown seed centre (largest brown blob inside the head) is the pivot
        centre = fill_holes(largest_component(brown & head))
        cy, cx = np.where(centre)
        self.pivot = (float(cx.mean()), float(cy.mean()))
        self.centre_r = 0.5 * (cx.max() - cx.min())
        centre_in = np.array(Image.fromarray(centre.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(5))) > 0
        self.centre_soft = np.array(Image.fromarray(centre_in.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32) / 255
        hys, hxs = np.where(head)
        self.head_box = (int(hxs.min()), int(hys.min()), int(hxs.max()) + 1, int(hys.max()) + 1)
        soft = np.array(Image.fromarray(head.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(2))).astype(np.float32) / 255
        self.head_soft = soft
        # bend profile: height above the pot rim
        yy = np.arange(self.oh, dtype=np.float32)
        self.t_rows = np.clip((self.pot_top - yy) / self.pot_top, 0, 1) ** 1.8
        self.pollen = [(0.0, 0.35), (0.33, -0.2), (0.66, 0.1), (0.5, 0.55), (0.15, -0.5)]

    def layer(self, t):
        ph = 2 * math.pi * t
        amp = 0.045 * self.oh
        bend = amp * (math.sin(ph) + 0.3 * math.sin(2 * ph + 0.7))
        base = np.array(self.obj)
        # 1. head turns a little around the seed centre (before the bend so it follows the stem)
        x0, y0, x1, y1 = self.head_box
        pad = 12
        x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(self.ow, x1 + pad), min(self.oh, y1 + pad)
        crop = Image.fromarray(base[y0:y1, x0:x1])
        m = self.head_soft[y0:y1, x0:x1]
        head_rgba = np.array(crop).astype(np.float32)
        head_rgba[..., 3] *= m
        head_img = Image.fromarray(head_rgba.astype(np.uint8))
        angle = 4.0 * math.sin(ph + 1.2) + 1.5 * math.sin(3 * ph)
        rot = rotate_pm(head_img, angle, (self.pivot[0] - x0, self.pivot[1] - y0))
        # paste: original head pixels faded out, rotated petal ring composited over, then the
        # untouched seed centre back on top so its highlight does not orbit
        body = np.array(crop).astype(np.float32)
        body[..., 3] *= (1 - m)
        layer_crop = Image.fromarray(body.astype(np.uint8))
        layer_crop.alpha_composite(rot)
        centre_rgba = np.array(crop).astype(np.float32)
        centre_rgba[..., 3] *= self.centre_soft[y0:y1, x0:x1]
        layer_crop.alpha_composite(Image.fromarray(centre_rgba.astype(np.uint8)))
        base[y0:y1, x0:x1] = np.array(layer_crop)
        # 2. wind bend (row shear growing with height)
        a = row_shift(base, self.t_rows * bend)
        img = Image.fromarray(a)
        # 3. pollen motes drifting up from the centre and fading out (own layer: ImageDraw on the
        #    RGBA image would overwrite pixels with the translucent colour instead of blending)
        motes = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(motes)
        for off, side in self.pollen:
            u = (t - off) % 1.0
            if u > 0.7:
                continue
            p = u / 0.7
            px = self.pivot[0] + self.centre_r * side + self.centre_r * 0.35 * math.sin(2 * math.pi * 2 * p + off * 9) + self.t_rows[int(self.pivot[1])] * bend
            py = self.pivot[1] - self.centre_r * 0.2 - self.oh * 0.16 * p
            alpha = int(255 * min(1.0, p * 6) * (1 - p) ** 0.8)
            rr = max(2, int(self.centre_r * 0.07 * (1 - 0.4 * p)))
            d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(255, 226, 120, alpha))
        img.alpha_composite(motes)
        return img

    def motion(self, t):
        ph = 2 * math.pi * t
        yaw = 3.0 * math.sin(ph - 0.6)
        return yaw, 0.0, 0.0, 1 + 0.02 * math.sin(ph), 1.0


SUBJECTS = {"bonsai": Bonsai, "sunflower": Sunflower, "macintosh": Macintosh}


# ----------------------------------------------------------------------------- render
def render(kind, cut, out_dir, n_frames=None):
    os.makedirs(out_dir, exist_ok=True)
    cls = SUBJECTS[kind]
    n = n_frames or cls.n_frames
    cw, ch = W * SS, H * SS
    src = Image.fromarray(cut)
    scale = (cls.fill * ch) / src.height
    if src.width * scale > 0.92 * cw:
        scale = 0.92 * cw / src.width
    obj = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
    subj = cls(obj)
    subj.n_frames = n
    ow, oh = obj.size
    cx, base = cw / 2, cls.base_y * ch
    pad = int(0.12 * max(ow, oh))
    paths = []
    for i in range(n):
        t = i / n
        yaw, dx, dy, sh_scale, sh_alpha = subj.motion(t)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        # contact shadow
        sh = Image.new("L", (cw, ch), 0)
        d = ImageDraw.Draw(sh)
        sw, shh = ow * 0.42 * sh_scale, oh * 0.06 * sh_scale
        d.ellipse([cx - sw, base - shh + 6 * SS * SCALE, cx + sw, base + shh + 6 * SS * SCALE], fill=int(110 * sh_alpha))
        sh = sh.filter(ImageFilter.GaussianBlur(10 * SS * SCALE * sh_scale))
        canvas.paste(Image.new("RGBA", (cw, ch), (20, 16, 12, 255)), (0, 0), sh)
        # object layer -> padded -> pseudo-3D yaw -> composite
        lay = subj.layer(t)
        big = Image.new("RGBA", (ow + 2 * pad, oh + 2 * pad), (0, 0, 0, 0))
        big.alpha_composite(lay, (pad, pad))
        big = yaw_rock(big, yaw)
        px = cx + dx * SS * SCALE - big.width / 2
        py = base + dy * SS * SCALE - (pad + oh)
        canvas.alpha_composite(big, (int(round(px)), int(round(py))))
        frame = canvas.resize((W, H), Image.LANCZOS)
        p = os.path.join(out_dir, f"frame_{i:03d}.png")
        frame.save(p)
        paths.append(p)
    return paths


if __name__ == "__main__":
    kind, src, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else None
    img = Image.open(src)
    if img.mode == "RGBA" and np.array(img)[..., 3].min() < 250:
        cut = np.array(img)
    else:
        cut = key_white(img, **KEY_PARAMS.get(kind, {}))
    cut = crop_to_alpha(cut)
    Image.fromarray(cut).save(os.path.join(os.path.dirname(out_dir.rstrip("/")) or ".", f"{kind}_cutout.png"))
    paths = render(kind, cut, out_dir, n)
    print(f"{kind}: {len(paths)} frames -> {out_dir}")
