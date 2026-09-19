"""Procedural OpenLava icons rendered with lava_sdf.

    python3 tool/sdf_scenes.py senna         assets/lava/senna
    python3 tool/sdf_scenes.py campfire      assets/lava/campfire
    python3 tool/sdf_scenes.py christmastree assets/lava/christmastree
    python3 tool/sdf_scenes.py senna --still 0.1 preview.png     # one frame, for look-dev

Every motion is a function of the loop phase t in [0, 1) built from whole multiples of 2*pi*t (or
frac(t + offset) for particles), so the last frame flows into the first.
"""
import math
import os
import sys
import tempfile
from multiprocessing import Pool

import numpy as np
from PIL import Image

import lava_sdf as sdf
from lava_sdf import F, Material, Scene, srgb, v3

TAU = 2.0 * math.pi


def sd_spheres(p, centres, radii):
    d = np.sqrt(((p[:, None, :] - centres[None]) ** 2).sum(-1)) - radii[None]
    return d.min(1)


def nearest(p, centres):
    return ((p[:, None, :] - centres[None]) ** 2).sum(-1).argmin(1)


def mix(a, b, k):
    return a + (b - a) * k[:, None]


# --------------------------------------------------------------------------------------------
class SennaHelmet(Scene):
    """Yellow full-face helmet with green and blue bands turning on its own axis."""

    frames, fps = 72, 24                 # one turn every three seconds
    view_height, look_at, pitch = 3.05, (0.0, 1.02, 0.0), 14.0
    bound_radius = 1.95
    shadow_strength = 0.26

    YELLOW, GREEN, BLUE = srgb(255, 200, 0), srgb(0, 132, 72), srgb(16, 44, 140)
    RUBBER = srgb(24, 24, 28)

    def __init__(self):
        self.materials = (
            Material(self.paint, spec=0.55, shininess=70.0, rim=0.22),
            Material(self.visor, spec=1.1, shininess=140.0, rim=0.35),
            Material(srgb(176, 180, 190), spec=0.8, shininess=60.0),
        )

    def to_object(self, p, t):
        q = p - v3(0.0, 1.16 + 0.045 * math.sin(TAU * 2.0 * t), 0.0)
        q = sdf.rot_y(q, -TAU * t)
        return sdf.rot_x(q, math.radians(-7.0))

    @staticmethod
    def visor_region(q):
        """Signed 2D distance (azimuth, height) to the rounded visor opening; < 0 inside."""
        phi = np.arctan2(q[:, 0], q[:, 2])
        dx = np.abs(phi) - 1.42
        dy = np.abs(q[:, 1] - 0.15 + 0.10 * np.cos(phi) - 0.10) - 0.17
        return (np.minimum(np.maximum(dx, dy), 0.0)
                + np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2) - 0.13)

    def parts(self, p, t):
        q = self.to_object(p, t)
        shell = sdf.sd_ellipsoid(q, v3(0, 0, 0), v3(0.98, 1.0, 1.10))
        chin = sdf.sd_ellipsoid(q, v3(0, -0.40, 0.36), v3(0.80, 0.44, 0.84))
        shell = sdf.smin(shell, chin, 0.22)
        shell = sdf.smax(shell, -(q[:, 1] + 0.74), 0.10)
        shell = np.maximum(shell, -self.visor_region(q) * 0.7)
        visor = sdf.sd_ellipsoid(q, v3(0, 0, 0), v3(0.945, 0.965, 1.065))
        visor = sdf.smax(visor, -(q[:, 1] + 0.70), 0.08)
        pivots = np.minimum(
            sdf.sd_ellipsoid(q, v3(0.965, 0.13, 0.20), v3(0.05, 0.12, 0.12)),
            sdf.sd_ellipsoid(q, v3(-0.965, 0.13, 0.20), v3(0.05, 0.12, 0.12)),
        )
        return [(shell, 0), (visor, 1), (pivots, 2)]

    def paint(self, scene, p, n, t):
        q = self.to_object(p, t)
        y = q[:, 1] + 0.09 * q[:, 2]      # the bands dip towards the front
        col = np.broadcast_to(self.YELLOW, q.shape).copy()

        def band(lo, hi, colour):
            k = sdf.smoothstep(lo - 0.012, lo + 0.012, y) * (1.0 - sdf.smoothstep(hi - 0.012, hi + 0.012, y))
            col[:] = mix(col, colour, k)

        band(0.50, 0.63, self.GREEN)
        band(0.385, 0.475, self.BLUE)
        band(-0.34, -0.25, self.BLUE)
        band(-0.49, -0.375, self.GREEN)
        gasket = 1.0 - sdf.smoothstep(0.035, 0.06, self.visor_region(q))
        trim = np.maximum(gasket, 1.0 - sdf.smoothstep(-0.69, -0.655, q[:, 1]))
        col = mix(col, self.RUBBER, trim)
        # lacquer: a faint studio softbox reflected in the clear coat
        r = 2.0 * (n @ scene.eye)[:, None] * n - scene.eye
        return col + (0.07 * sdf.smoothstep(0.35, 0.85, r[:, 1]) * (1.0 - trim))[:, None]

    def visor(self, scene, p, n, t):
        # Fake studio reflection: a bright softbox band across the upper part of the visor.
        r = 2.0 * (n @ scene.eye)[:, None] * n - scene.eye
        sky = sdf.smoothstep(0.15, 0.75, r[:, 1])
        return mix(np.broadcast_to(srgb(10, 12, 22), p.shape), srgb(120, 140, 185), sky * 0.85)


# --------------------------------------------------------------------------------------------
class Campfire(Scene):
    """Log teepee in a stone ring; the flame is the main light source of the icon."""

    frames, fps = 48, 30
    view_height, look_at, pitch = 3.1, (0.0, 0.92, 0.0), 24.0
    bound_radius = 2.05
    key_intensity = 0.50
    ambient_sky = srgb(190, 205, 255) * 0.42
    ambient_ground = srgb(255, 190, 140) * 0.22
    shadow_strength = 0.30

    def __init__(self):
        rng = np.random.default_rng(7)
        k = 10
        ang = np.arange(k) / k * TAU + 0.2
        self.stone_c = np.stack([1.16 * np.cos(ang), np.full(k, 0.13), 1.16 * np.sin(ang)], 1).astype(F)
        self.stone_r = np.stack([rng.uniform(0.24, 0.30, k), rng.uniform(0.16, 0.21, k),
                                 rng.uniform(0.22, 0.28, k)], 1).astype(F)
        self.stone_tone = rng.uniform(0.82, 1.12, k).astype(F)
        la = np.arange(5) / 5 * TAU + 0.55
        self.logs = [(v3(0.86 * math.cos(a), 0.10, 0.86 * math.sin(a)),
                      v3(-0.16 * math.cos(a), 1.02, -0.16 * math.sin(a))) for a in la]
        self.spark_seed = rng.uniform(0.0, 1.0, (7, 3)).astype(F)
        self.materials = (
            Material(self.stone, spec=0.10, shininess=10.0, rim=0.10),
            Material(self.wood, spec=0.12, shininess=12.0, rim=0.10),
            Material(srgb(30, 22, 20), spec=0.05, emissive=self.embers, rim=0.0),
            Material(srgb(0, 0, 0), spec=0.0, emissive=self.fire, rim=0.0),
            Material(srgb(0, 0, 0), spec=0.0, emissive=srgb(255, 190, 80) * 2.4, rim=0.0),
        )

    def flicker(self, t):
        return 1.0 + 0.16 * math.sin(TAU * 3 * t) + 0.09 * math.sin(TAU * 7 * t + 1.3) + 0.05 * math.sin(TAU * 11 * t)

    def lights(self, t):
        return [(v3(0.0, 0.78, 0.0), srgb(255, 150, 58), 3.4 * self.flicker(t), 0.85)]

    def sparks(self, t):
        s = self.spark_seed
        life = (t + s[:, 0]) % 1.0
        x = (s[:, 1] - 0.5) * 0.7 + 0.18 * np.sin(TAU * (life * 1.5 + s[:, 2]))
        z = (s[:, 2] - 0.5) * 0.7
        centres = np.stack([x, 1.0 + 1.55 * life, z], 1).astype(F)
        return centres, (0.042 * np.sin(np.pi * life) ** 0.7).astype(F)

    def flame(self, p, t):
        d = None
        for i, (ox, oz, h, r, ph) in enumerate([(0.0, 0.0, 1.30, 0.40, 0.0), (-0.24, 0.10, 0.92, 0.29, 0.37),
                                                (0.25, -0.06, 1.02, 0.30, 0.71), (0.04, 0.22, 0.78, 0.25, 0.53)]):
            q = p.copy()
            lift = np.clip(q[:, 1] - 0.30, 0.0, None)
            q[:, 0] -= ox + (0.13 * math.sin(TAU * (2 * t + ph)) + 0.05 * math.sin(TAU * (5 * t + ph * 3))) * lift ** 2
            q[:, 2] -= oz + 0.09 * math.cos(TAU * (3 * t + ph)) * lift ** 2
            height = h * (0.90 + 0.13 * math.sin(TAU * (4 * t + ph * 2.0)))
            tongue = sdf.sd_round_cone(q, v3(0, 0.42, 0), r, 0.025, height)
            d = tongue if d is None else sdf.smin(d, tongue, 0.16)
        return d

    def parts(self, p, t):
        stones = sdf.sd_ellipsoid(p[:, None, :], self.stone_c[None], self.stone_r[None]).min(1)
        logs = np.minimum.reduce([sdf.sd_capsule(p, a, b, 0.115) for a, b in self.logs])
        bed = sdf.sd_ellipsoid(p, v3(0, 0.06, 0), v3(0.70, 0.15, 0.70))
        sc, sr = self.sparks(t)
        return [(stones, 0), (logs, 1), (bed, 2), (self.flame(p, t) * 0.8, 3), (sd_spheres(p, sc, sr), 4)]

    def stone(self, scene, p, n, t):
        tone = self.stone_tone[nearest(p, self.stone_c)]
        return srgb(150, 146, 142)[None] * tone[:, None]

    def wood(self, scene, p, n, t):
        grain = 0.5 + 0.5 * np.sin(38.0 * p[:, 1] + 9.0 * p[:, 0] + 5.0 * np.sin(7.0 * p[:, 2]))
        char = sdf.smoothstep(0.75, 0.25, p[:, 1])      # tips inside the fire are charred
        col = mix(np.broadcast_to(srgb(122, 74, 40), p.shape), srgb(150, 96, 54), grain * 0.6)
        return mix(col, srgb(52, 34, 26), (1.0 - char) * 0.75)

    def embers(self, scene, p, n, v, t):
        veins = 0.5 + 0.5 * np.sin(11.0 * p[:, 0] + 4.0 * np.sin(9.0 * p[:, 2]) + TAU * 2 * t)
        heat = sdf.smoothstep(0.35, 0.95, veins) * sdf.smoothstep(0.70, 0.15, np.sqrt(p[:, 0] ** 2 + p[:, 2] ** 2))
        return srgb(255, 96, 18)[None] * (1.5 * heat * self.flicker(t))[:, None]

    def fire(self, scene, p, n, v, t):
        core = np.clip((n * v).sum(-1), 0.0, 1.0) ** 1.6
        height = np.clip((p[:, 1] - 0.35) / 1.35, 0.0, 1.0)
        col = mix(np.broadcast_to(srgb(255, 78, 8), p.shape), srgb(255, 176, 28), core)
        col = mix(col, srgb(255, 240, 170), core ** 2 * (1.0 - height) ** 1.5)
        return col * (1.75 * (1.0 - 0.35 * height))[:, None]


# --------------------------------------------------------------------------------------------
class ChristmasTree(Scene):
    """Snow-dusted tree rocking on its mound while the fairy lights blink in sequence."""

    frames, fps = 60, 30
    view_height, look_at, pitch = 3.45, (0.0, 1.32, 0.0), 13.0
    bound_radius = 2.25
    ambient_sky = srgb(225, 235, 255) * 0.58

    TIERS = [(0.34, 0.98, 0.34, 0.72), (0.86, 0.80, 0.25, 0.68), (1.33, 0.61, 0.17, 0.60), (1.74, 0.43, 0.05, 0.56)]
    LIGHT_COLOURS = [srgb(255, 214, 120), srgb(255, 64, 64), srgb(80, 220, 120), srgb(80, 150, 255), srgb(255, 120, 220)]
    BALL_COLOURS = [srgb(214, 40, 48), srgb(240, 180, 40), srgb(46, 100, 210)]

    def __init__(self):
        self.ball_c, self.ball_col = self.spiral(11, 0.50, 2.02, 0.35, 2.6, 0.085)
        self.light_c, self.light_col = self.spiral(16, 0.42, 2.12, 1.9, 3.4, 0.03)
        rng = np.random.default_rng(3)
        self.flakes = rng.uniform(0.0, 1.0, (9, 4)).astype(F)
        self.materials = (
            Material(self.foliage, spec=0.10, shininess=14.0, rim=0.16),
            Material(srgb(112, 70, 42), spec=0.08),
            Material(srgb(244, 248, 255), spec=0.18, shininess=20.0, rim=0.10),
            Material(self.balls, spec=0.95, shininess=90.0, rim=0.30),
            Material(srgb(20, 20, 20), spec=0.0, emissive=self.bulbs, rim=0.0),
            Material(srgb(255, 190, 40), spec=0.7, shininess=50.0, emissive=self.star, rim=0.3),
            Material(srgb(250, 252, 255), spec=0.0, emissive=srgb(255, 255, 255) * 0.35, rim=0.0),
        )

    def tree_radius(self, y):
        return float(np.interp(y, [0.34, 1.06, 1.06, 1.54, 1.54, 1.93, 1.93, 2.35],
                               [0.98, 0.34, 0.80, 0.25, 0.61, 0.17, 0.43, 0.05]))

    def spiral(self, count, y0, y1, phase, turns, lift):
        pts, cols = [], []
        for i in range(count):
            k = i / (count - 1)
            y = y0 + (y1 - y0) * k ** 0.85
            a = phase + turns * TAU * k
            r = self.tree_radius(y) + lift
            pts.append([r * math.cos(a), y, r * math.sin(a)])
            cols.append(i)
        return np.array(pts, F), np.array(cols)

    def angle(self, t):
        return 0.55 * math.sin(TAU * t)

    def to_object(self, p, t):
        return sdf.rot_y(p, -self.angle(t))

    def blink(self, t):
        i = np.arange(len(self.light_c))
        wave = np.sin(TAU * (2.0 * t + i * 0.31))
        return (0.10 + 0.90 * sdf.smoothstep(-0.2, 0.6, wave)).astype(F)

    def lights(self, t):
        world = sdf.rot_y(self.light_c, self.angle(t))
        power = self.blink(t)
        out = [(world[i], self.LIGHT_COLOURS[i % 5], 0.55 * float(power[i]), 9.0) for i in range(len(world))]
        return out + [(v3(0.0, 2.62, 0.0), srgb(255, 205, 90), 0.7 + 0.2 * math.sin(TAU * 2 * t), 3.0)]

    def snow(self, t):
        f = self.flakes
        life = (t + f[:, 0]) % 1.0
        x = (f[:, 1] - 0.5) * 3.3 + 0.10 * np.sin(TAU * (life + f[:, 3]))
        z = (f[:, 2] - 0.5) * 1.6 + 0.9
        centres = np.stack([x, 2.95 - 2.9 * life, z], 1).astype(F)
        return centres, (0.040 * np.sin(np.pi * life) ** 0.5).astype(F)

    def parts(self, p, t):
        q = self.to_object(p, t)
        theta = np.arctan2(q[:, 2], q[:, 0])
        lobes = 1.0 + 0.085 * np.cos(8.0 * theta + 2.0 * q[:, 1])      # scalloped branch tips
        ql = q.copy()
        ql[:, 0] /= lobes
        ql[:, 2] /= lobes
        tree = None
        for y0, r1, r2, h in self.TIERS:
            tier = sdf.sd_round_cone(ql, v3(0, y0, 0), r1 * 0.80, r2 * 0.6, h)
            tier = sdf.smax(tier, -(ql[:, 1] - (y0 - 0.05)), 0.10)       # flat-ish underside
            tree = tier if tree is None else sdf.smin(tree, tier, 0.07)
        trunk = sdf.sd_cylinder(q, v3(0, 0.0, 0), 0.17, 0.5, 0.03)
        mound = sdf.sd_ellipsoid(p, v3(0, -0.02, 0), v3(1.40, 0.24, 1.40))
        balls = sd_spheres(q, self.ball_c, np.full(len(self.ball_c), 0.092, F))
        bulbs = sd_spheres(q, self.light_c, np.full(len(self.light_c), 0.050, F))
        star = sdf.sd_star_prism(q, v3(0, 2.58, 0), 0.30, 0.46, 0.055, 0.03)
        fc, fr = self.snow(t)
        return [(tree * 0.85, 0), (trunk, 1), (mound, 2), (balls, 3), (bulbs, 4), (star, 5), (sd_spheres(p, fc, fr), 6)]

    def foliage(self, scene, p, n, t):
        q = self.to_object(p, t)
        theta = np.arctan2(q[:, 2], q[:, 0])
        green = mix(np.broadcast_to(srgb(22, 96, 58), p.shape), srgb(52, 150, 84),
                    np.clip(0.5 + 0.5 * n[:, 1] + 0.2 * np.sin(8.0 * theta), 0.0, 1.0))
        snow = sdf.smoothstep(0.42, 0.62, n[:, 1] + 0.10 * np.sin(5.0 * theta + 6.0 * q[:, 1]))
        return mix(green, srgb(246, 250, 255), snow)

    def balls(self, scene, p, n, t):
        idx = nearest(self.to_object(p, t), self.ball_c)
        return np.array(self.BALL_COLOURS, F)[self.ball_col[idx] % 3]

    def bulbs(self, scene, p, n, v, t):
        idx = nearest(self.to_object(p, t), self.light_c)
        return np.array(self.LIGHT_COLOURS, F)[idx % 5] * (2.6 * self.blink(t)[idx])[:, None]

    def star(self, scene, p, n, v, t):
        return srgb(255, 196, 48)[None] * np.full((p.shape[0], 1), 0.55 + 0.25 * math.sin(TAU * 2 * t), F)


SCENES = {"senna": SennaHelmet, "campfire": Campfire, "christmastree": ChristmasTree}


def _render(job):
    name, index, total, ss, path = job
    Image.fromarray(sdf.render_frame(SCENES[name](), index / total, ss)).save(path)
    return path


def main(argv):
    name = argv[0]
    scene = SCENES[name]()
    if "--still" in argv:
        at = argv.index("--still")
        Image.fromarray(sdf.render_frame(scene, float(argv[at + 1]), 3)).save(argv[at + 2])
        return
    out_dir = argv[1]
    ss = int(argv[argv.index("--ss") + 1]) if "--ss" in argv else 3
    frames_dir = argv[argv.index("--frames-dir") + 1] if "--frames-dir" in argv else tempfile.mkdtemp(prefix=f"lava_{name}_")
    os.makedirs(frames_dir, exist_ok=True)
    jobs = [(name, i, scene.frames, ss, os.path.join(frames_dir, f"frame_{i:03d}.png")) for i in range(scene.frames)]
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        paths = pool.map(_render, jobs)
    print(f"rendered {len(paths)} frames -> {frames_dir}")

    from openlava_encode import encode
    encode(sorted(paths), out_dir, fps=scene.fps)


if __name__ == "__main__":
    main(sys.argv[1:])
