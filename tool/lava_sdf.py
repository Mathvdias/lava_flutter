"""Procedural 3D icon renderer for OpenLava bundles.

A small numpy SDF ray marcher that renders loopable RGBA frame sequences in the look of the Airbnb
Lava icons: orthographic three-quarter view, soft top-left key light, satin materials, ambient
occlusion, a soft contact shadow and no background. Unlike keyed 2D stills it is real 3D, so an
object can turn on its own axis, and it supports emissive materials, point lights and bloom, so a
flame or a fairy light actually lights the rest of the icon.

Scenes live in sdf_scenes.py; this module only knows about distances, materials and light.
"""
import math
import os

import numpy as np

# OpenLava canvas: 180x162 like the Airbnb samples; LAVA_SCALE=2 renders the 360x324 large-preview
# variant (pixel-sized blurs scale with it).
SCALE = int(os.environ.get("LAVA_SCALE", "1"))
W, H = 180 * SCALE, 162 * SCALE

F = np.float32


def v3(x, y, z):
    return np.array([x, y, z], F)


def norm(v):
    v = np.asarray(v, F)
    return v / np.linalg.norm(v)


def srgb(r, g, b):
    """sRGB 0-255 -> linear float."""
    return (np.array([r, g, b], F) / 255.0) ** 2.2


# --------------------------------------------------------------------------------------------
# Distance functions. `p` is (N, 3); everything returns (N,).
# --------------------------------------------------------------------------------------------
def length(a):
    return np.sqrt((a * a).sum(-1))


def sd_sphere(p, c, r):
    return length(p - c) - r


def sd_ellipsoid(p, c, r):
    q = p - c
    k0 = length(q / r)
    k1 = length(q / (r * r))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def sd_capsule(p, a, b, r):
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0.0, 1.0)
    return length(pa - h[:, None] * ba) - r


def sd_round_cone(p, base, r1, r2, h):
    """Vertical cone with spherical caps: radius r1 at `base`, r2 at base + (0, h, 0)."""
    q = p - base
    qx = np.sqrt(q[:, 0] ** 2 + q[:, 2] ** 2)
    qy = q[:, 1]
    b = (r1 - r2) / h
    a = math.sqrt(max(1.0 - b * b, 1e-6))
    k = -b * qx + a * qy
    return np.where(
        k < 0.0,
        np.sqrt(qx * qx + qy * qy) - r1,
        np.where(k > a * h, np.sqrt(qx * qx + (qy - h) ** 2) - r2, a * qx + b * qy - r1),
    )


def sd_cylinder(p, base, r, h, rounding=0.0):
    q = p - base
    dx = np.sqrt(q[:, 0] ** 2 + q[:, 2] ** 2) - (r - rounding)
    dy = np.abs(q[:, 1] - h * 0.5) - (h * 0.5 - rounding)
    return (np.minimum(np.maximum(dx, dy), 0.0)
            + np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2) - rounding)


def sd_torus(p, c, R, r):
    q = p - c
    return np.sqrt((np.sqrt(q[:, 0] ** 2 + q[:, 2] ** 2) - R) ** 2 + q[:, 1] ** 2) - r


def sd_star_prism(p, c, r, rf, half_depth, rounding=0.02):
    """Five-pointed star in the XY plane extruded along Z."""
    q = p - c
    x, y = np.abs(q[:, 0]), q[:, 1].copy()
    k1x, k1y = 0.809016994375, -0.587785252292
    for kx in (k1x, -k1x):
        d = 2.0 * np.maximum(kx * x + k1y * y, 0.0)
        x, y = x - d * kx, y - d * k1y
    x = np.abs(x)
    y = y - r
    bax, bay = rf * (-k1y) - 0.0, rf * k1x - 1.0
    h = np.clip((x * bax + y * bay) / (bax * bax + bay * bay), 0.0, r)
    d2 = np.sqrt((x - bax * h) ** 2 + (y - bay * h) ** 2) * np.sign(y * bax - x * bay)
    dz = np.abs(q[:, 2]) - half_depth
    return (np.minimum(np.maximum(d2, dz), 0.0)
            + np.sqrt(np.maximum(d2, 0.0) ** 2 + np.maximum(dz, 0.0) ** 2) - rounding)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def rot_y(p, angle):
    c, s = math.cos(angle), math.sin(angle)
    out = p.copy()
    out[:, 0] = c * p[:, 0] + s * p[:, 2]
    out[:, 2] = -s * p[:, 0] + c * p[:, 2]
    return out


def rot_x(p, angle):
    c, s = math.cos(angle), math.sin(angle)
    out = p.copy()
    out[:, 1] = c * p[:, 1] - s * p[:, 2]
    out[:, 2] = s * p[:, 1] + c * p[:, 2]
    return out


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------------------------
# Scene contract
# --------------------------------------------------------------------------------------------
class Material:
    def __init__(self, albedo, spec=0.25, shininess=24.0, emissive=None, rim=0.18):
        self.albedo = albedo          # linear rgb, or callable(scene, p, n, t) -> (N, 3)
        self.spec = spec
        self.shininess = shininess
        self.emissive = emissive      # None, linear rgb, or callable(scene, p, n, v, t) -> (N, 3)
        self.rim = rim


class Scene:
    """Subclasses describe geometry as a list of (distance, material index) parts."""

    frames = 48
    fps = 30
    view_height = 3.2             # world units covered by the frame's height
    look_at = (0.0, 1.0, 0.0)
    azimuth, pitch = 0.0, 16.0    # camera orbit in degrees
    ground_y = 0.0
    bound_radius = 2.4            # everything (including particles) fits this sphere
    shadow_strength = 0.34
    key_intensity = 0.95
    ambient_sky = srgb(235, 240, 255) * 0.62
    ambient_ground = srgb(255, 236, 214) * 0.30
    exposure = 1.0
    materials = ()

    def parts(self, p, t):
        raise NotImplementedError

    def lights(self, t):
        """Point lights: list of (position, linear rgb, intensity, falloff)."""
        return []

    def dist(self, p, t):
        return np.minimum.reduce([d for d, _ in self.parts(p, t)])

    def material_ids(self, p, t):
        parts = self.parts(p, t)
        winner = np.argmin(np.stack([d for d, _ in parts]), axis=0)
        return np.array([m for _, m in parts])[winner]


# --------------------------------------------------------------------------------------------
# Ray marching
# --------------------------------------------------------------------------------------------
def march(scene, ro, rd, t, t0, t1, steps=90, eps=0.0018, relax=0.85):
    n = ro.shape[0]
    depth = t0.copy()
    hit = np.zeros(n, bool)
    active = np.arange(n)
    for _ in range(steps):
        if active.size == 0:
            break
        d = scene.dist(ro[active] + rd[active] * depth[active, None], t)
        depth[active] += d * relax
        done = d < eps
        hit[active[done]] = True
        active = active[~done & (depth[active] < t1[active])]
    return hit, depth


def normals(scene, p, t, e=0.0025):
    k = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], F)
    n = sum(k[i] * scene.dist(p + k[i] * e, t)[:, None] for i in range(4))
    return n / np.maximum(length(n)[:, None], 1e-8)


def soft_shadow(scene, p, l, t, k=9.0, tmax=4.0, steps=28):
    n = p.shape[0]
    res = np.ones(n, F)
    depth = np.full(n, 0.03, F)
    active = np.arange(n)
    for _ in range(steps):
        if active.size == 0:
            break
        d = scene.dist(p[active] + l * depth[active, None], t)
        res[active] = np.minimum(res[active], k * d / depth[active])
        depth[active] += np.clip(d, 0.025, 0.25)
        active = active[(res[active] > 0.004) & (depth[active] < tmax)]
    return np.clip(res, 0.0, 1.0)


def ambient_occlusion(scene, p, n, t):
    occ = np.zeros(p.shape[0], F)
    scale = 1.0
    for i in range(5):
        h = 0.02 + 0.11 * i
        occ += (h - scene.dist(p + n * h, t)) * scale
        scale *= 0.72
    return np.clip(1.0 - 1.6 * occ, 0.0, 1.0)


def gaussian_blur(img, sigma):
    """Frequency-domain gaussian; `img` is (h, w) or (h, w, c)."""
    h, w = img.shape[:2]
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    kernel = np.exp(-2.0 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    if img.ndim == 2:
        return np.fft.irfft2(np.fft.rfft2(img) * kernel, s=(h, w)).astype(F)
    return np.stack([gaussian_blur(img[..., c], sigma) for c in range(img.shape[2])], -1)


# --------------------------------------------------------------------------------------------
# Frame rendering
# --------------------------------------------------------------------------------------------
KEY_DIR = norm([-0.48, 0.78, 0.52])        # soft top-left key, slightly in front
SHADOW_DIR = norm([-0.10, 1.0, 0.12])      # contact shadow falls almost straight down


def render_frame(scene, t, ss=3):
    """Returns a (H, W, 4) uint8 straight-alpha frame for loop phase t in [0, 1)."""
    w, h = W * ss, H * ss
    az, pi = math.radians(scene.azimuth), math.radians(scene.pitch)
    eye = v3(math.sin(az) * math.cos(pi), math.sin(pi), math.cos(az) * math.cos(pi))
    right = v3(math.cos(az), 0.0, -math.sin(az))
    up = np.cross(eye, right).astype(F)
    fwd = -eye
    scene.eye = eye

    half_h = scene.view_height * 0.5
    half_w = half_h * W / H
    u = ((np.arange(w, dtype=F) + 0.5) / w * 2.0 - 1.0) * half_w
    v = (1.0 - (np.arange(h, dtype=F) + 0.5) / h * 2.0) * half_h
    uu, vv = np.meshgrid(u, v)
    centre = np.asarray(scene.look_at, F)
    ro_all = (centre + eye * 12.0 + uu.reshape(-1, 1) * right + vv.reshape(-1, 1) * up).astype(F)

    rgb = np.zeros((h * w, 3), F)      # premultiplied linear colour
    alpha = np.zeros(h * w, F)
    glow = np.zeros((h * w, 3), F)     # emissive energy that feeds the bloom
    ground = np.zeros(h * w, F)        # contact shadow, blurred before it joins the alpha

    # Rays that cannot touch the bounding sphere never march.
    oc = ro_all - centre
    b = oc @ fwd
    disc = scene.bound_radius ** 2 - ((oc * oc).sum(-1) - b * b)
    cand = np.nonzero(disc > 0.0)[0]
    sq = np.sqrt(disc[cand])
    ro = ro_all[cand]
    rd = np.broadcast_to(fwd, ro.shape)
    hit, depth = march(scene, ro, rd, t, (-b[cand] - sq).astype(F), (-b[cand] + sq).astype(F))

    lights = scene.lights(t)

    idx = cand[hit]
    if idx.size:
        p = ro[hit] + fwd * depth[hit, None]
        n = normals(scene, p, t)
        ids = scene.material_ids(p, t)
        view = np.broadcast_to(eye, p.shape)

        albedo = np.zeros_like(p)
        spec_k = np.zeros(p.shape[0], F)
        shin = np.ones(p.shape[0], F)
        rim_k = np.zeros(p.shape[0], F)
        emis = np.zeros_like(p)
        for mid, mat in enumerate(scene.materials):
            m = ids == mid
            if not m.any():
                continue
            a = mat.albedo
            albedo[m] = a(scene, p[m], n[m], t) if callable(a) else a
            spec_k[m], shin[m], rim_k[m] = mat.spec, mat.shininess, mat.rim
            if mat.emissive is not None:
                e = mat.emissive
                emis[m] = e(scene, p[m], n[m], view[m], t) if callable(e) else e

        ao = ambient_occlusion(scene, p, n, t)
        ndl = np.clip(n @ KEY_DIR, 0.0, 1.0)
        shadow = np.ones_like(ndl)
        lit = ndl > 0.0
        shadow[lit] = soft_shadow(scene, p[lit] + n[lit] * 0.01, KEY_DIR, t)
        shadow = 0.30 + 0.70 * shadow          # bounce light keeps shadows airy

        hemi = (0.5 + 0.5 * n[:, 1])[:, None]
        ambient = scene.ambient_ground * (1.0 - hemi) + scene.ambient_sky * hemi
        fill = np.clip(n @ eye, 0.0, 1.0)[:, None] * 0.22
        diffuse = ambient * ao[:, None] + (scene.key_intensity * ndl * shadow)[:, None] + fill * ao[:, None]

        half = norm(KEY_DIR + eye)
        spec = spec_k * np.clip(n @ half, 0.0, 1.0) ** shin * shadow
        fres = (1.0 - np.clip(n @ eye, 0.0, 1.0)) ** 3.0
        col = albedo * diffuse + spec[:, None] + (rim_k * fres * ao)[:, None] * scene.ambient_sky * 1.5

        for lp, lc, li, lf in lights:
            lv = lp - p
            d2 = (lv * lv).sum(-1)
            ld = lv / np.sqrt(d2)[:, None]
            wrap = np.clip(((n * ld).sum(-1) + 0.35) / 1.35, 0.0, 1.0)
            col += albedo * lc * (li * wrap / (1.0 + lf * d2))[:, None]

        col += emis
        rgb[idx] = col
        alpha[idx] = 1.0
        glow[idx] = emis

    # Ground pass: soft contact shadow plus whatever the point lights throw on the floor.
    miss = cand[~hit]
    if miss.size and abs(fwd[1]) > 1e-4:
        tg = (scene.ground_y - ro_all[miss, 1]) / fwd[1]
        g = ro_all[miss] + fwd * tg[:, None]
        near = ((g - centre)[:, [0, 2]] ** 2).sum(-1) < (scene.bound_radius * 1.15) ** 2
        gi, g = miss[near], g[near]
        if gi.size:
            sh = soft_shadow(scene, g + v3(0, 0.01, 0), SHADOW_DIR, t, k=3.2, tmax=3.2, steps=22)
            # the shadow dies out before it can reach the edge of the frame
            reach = np.sqrt(((g - centre)[:, [0, 2]] ** 2).sum(-1)) / scene.bound_radius
            ground[gi] = scene.shadow_strength * (1.0 - sh) * (1.0 - smoothstep(0.45, 0.80, reach))
            for lp, lc, li, lf in lights:
                d2 = ((lp - g) ** 2).sum(-1)
                e = lc * (0.55 * li * (lp[1] - scene.ground_y) / np.sqrt(d2) / (1.0 + lf * d2))[:, None]
                rgb[gi] += e * (0.35 + 0.65 * sh)[:, None]
                alpha[gi] = np.maximum(alpha[gi], np.clip(e.max(-1) * 1.4, 0.0, 0.85))

    rgb = rgb.reshape(h, w, 3)
    alpha = alpha.reshape(h, w)
    if ground.any():
        soft = np.clip(gaussian_blur(ground.reshape(h, w), 3.0 * ss * SCALE), 0.0, 1.0)
        alpha = alpha + (1.0 - alpha) * soft * (alpha < 1.0)
    glow = glow.reshape(h, w, 3)

    if glow.any():
        bloom = 0.55 * gaussian_blur(glow, 1.6 * ss * SCALE) + 0.50 * gaussian_blur(glow, 5.5 * ss * SCALE)
        bloom = np.maximum(bloom, 0.0)
        rgb += bloom
        alpha = np.maximum(alpha, np.clip(bloom.max(-1) * 1.25, 0.0, 1.0))

    # Box downsample in linear light, then tone map, saturate and encode.
    rgb = rgb.reshape(H, ss, W, ss, 3).mean((1, 3))
    alpha = alpha.reshape(H, ss, W, ss).mean((1, 3))
    straight = rgb / np.maximum(alpha, 1e-4)[..., None] * scene.exposure
    straight = straight / (1.0 + 0.18 * straight) * 1.18
    luma = straight @ np.array([0.2126, 0.7152, 0.0722], F)
    straight = luma[..., None] + (straight - luma[..., None]) * 1.12
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = (np.clip(straight, 0.0, 1.0) ** (1.0 / 2.2) * 255.0 + 0.5).astype(np.uint8)
    out[..., 3] = (np.clip(alpha, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    out[out[..., 3] == 0] = 0
    return out
