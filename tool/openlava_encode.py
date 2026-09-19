"""OpenLava encoder: frames (RGBA PNG, same size) -> key image, diff atlas, manifest.json.

Format (identical to the Airbnb sample assets):
  - frames[0]  = {"type": "key", "imageIndex": 0}      -> image_1 is the full first frame
  - frames[n]  = {"type": "diff", "diffs": [[srcImage, srcTile, countX, countY, dstTile], ...]}
    Each diff blits a countX x countY block of cellSize tiles from srcImage (tile index in that
    image's grid, tilesPerRow = ceil(imageWidth / cellSize)) to the destination tile index.
    A diff frame is drawn on a cleared canvas, so it must list every tile it needs.

Packing follows OpenLava's Docs/packing.md:
  1. every tile of every frame gets an id (identical pixels -> same id; colour under alpha 0 is
     zeroed first so invisible differences never count);
  2. per frame, fully transparent tiles cost nothing (the canvas starts cleared), tiles found in the
     key image are copied from it, tiles already in the atlas are referenced again - growing the
     largest rectangle that is contiguous both in the frame and in the source - and only tiles never
     seen before become a new patch;
  3. patches are shelf-packed (tallest first) and the references resolved to atlas tile indices.
A looping motion that passes through the same pose twice (any sin-driven rock or bob does) is
therefore stored once, and the corners of the bounding box around a round object are free.

lava_flutter composes frames 1:1 with nearest sampling before scaling, so neighbouring atlas tiles
cannot bleed into each other and no gutter is needed (`gutter=1` restores one for players that blit
scaled tiles straight from the atlas).
"""
import json, math, sys, os
import numpy as np
from PIL import Image


def load_frames(paths):
    frames = []
    for p in paths:
        a = np.array(Image.open(p).convert("RGBA"))
        a[a[..., 3] == 0] = 0
        frames.append(a)
    return frames


def pad(img, cs):
    h, w = img.shape[:2]
    H, W = math.ceil(h / cs) * cs, math.ceil(w / cs) * cs
    out = np.zeros((H, W, 4), np.uint8)
    out[:h, :w] = img
    return out


class TileTable:
    """Tile pixels <-> id. Id 0 is the fully transparent tile."""

    def __init__(self, cell):
        self.cell = cell
        self.ids = {np.zeros((cell, cell, 4), np.uint8).tobytes(): 0}
        self.pixels = [np.zeros((cell, cell, 4), np.uint8)]

    def grid(self, frame):
        rows, cols = frame.shape[0] // self.cell, frame.shape[1] // self.cell
        g = np.zeros((rows, cols), np.int64)
        for r in range(rows):
            for c in range(cols):
                tile = frame[r * self.cell:(r + 1) * self.cell, c * self.cell:(c + 1) * self.cell]
                key = tile.tobytes()
                if key not in self.ids:
                    self.ids[key] = len(self.pixels)
                    self.pixels.append(tile.copy())
                g[r, c] = self.ids[key]
        return g


def grow(frame, free, r, c, source, sr, sc):
    """Largest rectangle (width first, then height) starting at frame[r, c] / source[sr, sc] whose
    tiles are still free and equal in both grids. -> (w, h)"""
    rows, cols = frame.shape
    srows, scols = source.shape
    w = 0
    while (c + w < cols and sc + w < scols and free[r, c + w]
           and frame[r, c + w] == source[sr, sc + w]):
        w += 1
    h = 1
    while (r + h < rows and sr + h < srows and free[r + h, c:c + w].all()
           and np.array_equal(frame[r + h, c:c + w], source[sr + h, sc:sc + w])):
        h += 1
    return w, h


def pack(patches, tpr, gutter):
    """Shelf packing, tallest first. -> [(x_tile, y_tile)] per patch, atlas height in tiles."""
    order = sorted(range(len(patches)), key=lambda i: (-patches[i].shape[0], -patches[i].shape[1]))
    pos = [None] * len(patches)
    x = y = shelf = 0
    for i in order:
        ph, pw = patches[i].shape
        if x + pw > tpr:
            y, x, shelf = y + shelf + gutter, 0, 0
        pos[i] = (x, y)
        x += pw + gutter
        shelf = max(shelf, ph)
    return pos, y + shelf


def save_image(pixels, base, fmt, quality):
    """-> file name. quality >= 100 means lossless where the format has a sane lossless mode."""
    path = f"{base}.{fmt}"
    img = Image.fromarray(pixels)
    if fmt == "png":
        img.save(path, optimize=True)
    elif fmt == "webp":
        if quality >= 100:
            img.save(path, lossless=True, method=6)
        else:
            # WebP is 4:2:0 only: thin saturated lines (the helmet stripes) wash out below 100
            img.save(path, quality=quality, method=6, alpha_quality=100)
    elif fmt == "avif":
        # 4:4:4 keeps those lines crisp at a fraction of the bytes; this is what Airbnb ships
        img.save(path, quality=quality, subsampling="4:4:4", speed=2)
    else:
        raise ValueError(fmt)
    return os.path.basename(path)


def encode(frame_paths, out_dir, fps=30, cell=32, diff_w=2048, density=2, gutter=0,
           fmt="png", quality=100, fallback=None):
    """`fmt` / `quality`: png (lossless), webp (100 = lossless) or avif. `fallback=(fmt, quality)`
    writes a second copy of both images and lists it as `fallbackUrl` for decoders without AVIF."""
    frames = [pad(f, cell) for f in load_frames(frame_paths)]
    h, w = Image.open(frame_paths[0]).size[::-1]
    tpr = diff_w // cell
    if diff_w % cell or math.ceil(frames[0].shape[1] / cell) > tpr:
        raise ValueError(f"diff_w={diff_w} must be a multiple of {cell} and at least as wide as a frame")
    table = TileTable(cell)
    grids = [table.grid(f) for f in frames]
    key = grids[0]

    key_at = {}                                    # tile id -> first position in the key image
    for r in range(key.shape[0]):
        for c in range(key.shape[1]):
            key_at.setdefault(int(key[r, c]), (r, c))

    patches, placed = [], {}                       # patch id grids; tile id -> [(patch, r, c)]
    plans = []                                     # per frame: [("key" | patch index, sr, sc, w, h, r, c)]
    cols = key.shape[1]
    for g in grids[1:]:
        free = g != 0                              # transparent tiles need no blit
        plan = []
        for r, c in zip(*np.where(free & (g == key))):      # unchanged: straight from the key
            if free[r, c]:
                bw, bh = grow(g, free, r, c, key, r, c)
                free[r:r + bh, c:c + bw] = False
                plan.append(("key", r, c, bw, bh, r, c))
        for r, c in zip(*np.where(free)):
            if not free[r, c]:
                continue
            tid = int(g[r, c])
            best = None
            if tid in key_at:                                # the same tile elsewhere in the key
                sr, sc = key_at[tid]
                bw, bh = grow(g, free, r, c, key, sr, sc)
                best = (bw * bh, "key", sr, sc, bw, bh)
            for pi, pr, pc in placed.get(tid, ()):           # already in the atlas
                bw, bh = grow(g, free, r, c, patches[pi], pr, pc)
                if best is None or bw * bh > best[0]:
                    best = (bw * bh, pi, pr, pc, bw, bh)
            if best is None:                                 # never seen: a new patch of new tiles
                fresh = free & ~np.isin(g, list(placed.keys()) + list(key_at.keys()))
                bw, bh = grow(g, fresh, r, c, g, r, c)
                pi = len(patches)
                patches.append(g[r:r + bh, c:c + bw].copy())
                for pr in range(bh):
                    for pc in range(bw):
                        placed.setdefault(int(g[r + pr, c + pc]), []).append((pi, pr, pc))
                best = (bw * bh, pi, 0, 0, bw, bh)
            _, src, sr, sc, bw, bh = best
            free[r:r + bh, c:c + bw] = False
            plan.append((src, sr, sc, bw, bh, r, c))
        plans.append(plan)

    pos, atlas_rows = pack(patches, tpr, gutter)
    atlas = np.zeros((max(1, atlas_rows) * cell, tpr * cell, 4), np.uint8)
    for (ax, ay), patch in zip(pos, patches):
        for pr in range(patch.shape[0]):
            for pc in range(patch.shape[1]):
                y, x = (ay + pr) * cell, (ax + pc) * cell
                atlas[y:y + cell, x:x + cell] = table.pixels[int(patch[pr, pc])]

    manifest_frames = [{"type": "key", "imageIndex": 0}]
    for plan in plans:
        diffs = []
        for src, sr, sc, bw, bh, r, c in sorted(plan, key=lambda d: d[0] != "key"):   # key blits first: two batches
            if src == "key":
                diffs.append([0, int(sr * cols + sc), int(bw), int(bh), int(r * cols + c)])
            else:
                ax, ay = pos[src]
                diffs.append([1, int((ay + sr) * tpr + ax + sc), int(bw), int(bh), int(r * cols + c)])
        manifest_frames.append({"type": "diff", "diffs": diffs})

    if fallback and fallback[0] == fmt:
        raise ValueError(f"the fallback would overwrite the primary image (both are .{fmt})")
    os.makedirs(out_dir, exist_ok=True)
    images, written = [], set()
    for name, pixels in (("image_1", frames[0][:h, :w]), ("image_2", atlas)):
        entry = {"url": save_image(pixels, os.path.join(out_dir, name), fmt, quality)}
        if fallback:
            entry["fallbackUrl"] = save_image(pixels, os.path.join(out_dir, name), *fallback)
        written.update(entry.values())
        images.append(entry)
    for name in os.listdir(out_dir):               # stale formats go only once the new files exist
        if name.startswith(("image_1.", "image_2.")) and name not in written:
            os.remove(os.path.join(out_dir, name))
    manifest = {
        "version": 1, "fps": fps, "cellSize": cell, "diffImageSize": diff_w,
        "width": w, "height": h, "density": density, "alpha": True,
        "images": images,
        "frames": manifest_frames,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, separators=(",", ":"))
    tiles = sum(int(p.size) for p in patches)
    naive = sum(int((g != key).any()) * int(np.ptp(np.where(g != key)[0]) + 1) * int(np.ptp(np.where(g != key)[1]) + 1)
                for g in grids[1:] if (g != key).any())
    print(f"{out_dir}: {len(frames)} frames, {len(patches)} patches, {tiles} atlas tiles "
          f"(one block per frame would need {naive}), atlas {atlas.shape[1]}x{atlas.shape[0]}")


def decode_frames(bundle_dir, cell=None, which="url"):
    """Re-render every frame of a bundle the way the players do. -> list of HxWx4 uint8 arrays"""
    m = json.load(open(os.path.join(bundle_dir, "manifest.json")))
    cell = cell or m.get("cellSize", 32)
    imgs = [np.array(Image.open(os.path.join(bundle_dir, i.get(which) or i["url"])).convert("RGBA")) for i in m["images"]]
    w, h = m["width"], m["height"]
    cols = math.ceil(w / cell)
    tpr = [math.ceil(im.shape[1] / cell) for im in imgs]
    out = []
    for fr in m["frames"]:
        canvas = np.zeros((math.ceil(h / cell) * cell, cols * cell, 4), np.uint8)
        if fr["type"] == "key":
            im = imgs[fr["imageIndex"]]
            canvas[:im.shape[0], :im.shape[1]] = im
        else:
            for si, st, cx, cy, d in fr["diffs"]:
                im = imgs[si]
                sx, sy = (st % tpr[si]) * cell, (st // tpr[si]) * cell
                dx, dy = (d % cols) * cell, (d // cols) * cell
                blk = im[sy:sy + cy * cell, sx:sx + cx * cell]
                canvas[dy:dy + blk.shape[0], dx:dx + blk.shape[1]] = blk
        out.append(canvas[:h, :w])
    return out, m


def decode_check(out_dir, frame_paths, cell=32, which="url"):
    """Decode the bundle like a player and compare with the source frames (premultiplied: colour
    under transparent pixels is not visible)."""
    def premultiplied(a):
        a = a.astype(np.float32)
        return np.dstack([a[..., :3] * a[..., 3:4] / 255.0, a[..., 3:4]])

    decoded, m = decode_frames(out_dir, cell, which)
    src = load_frames(frame_paths)
    worst, total = 0, 0.0
    for got, want in zip(decoded, src):
        err = np.abs(premultiplied(got) - premultiplied(want))
        worst, total = max(worst, int(err.max())), total + float(err.mean())
    print(f"decode check {out_dir} [{m['images'][1].get(which)}]: max abs pixel error = {worst}, "
          f"mean = {total / len(decoded):.3f} (lossless bundles must report 0)")
    return worst


if __name__ == "__main__":
    # openlava_encode.py <out_dir> [--fps N] [--png | --webp Q | --avif Q] [--fallback-webp Q] [--gutter N] frames...
    # openlava_encode.py <out_dir> --from-bundle <lossless bundle dir> ...   (repack an existing bundle)
    args = sys.argv[1:]
    opts = {}

    def take(flag, cast=int):
        if flag in args:
            at = args.index(flag)
            value = cast(args[at + 1])
            del args[at:at + 2]
            return value
        return None

    if (v := take("--fps")) is not None:
        opts["fps"] = v
    if (v := take("--gutter")) is not None:
        opts["gutter"] = v
    if (v := take("--webp")) is not None:
        opts.update(fmt="webp", quality=v)
    if (v := take("--avif")) is not None:
        opts.update(fmt="avif", quality=v)
    if (v := take("--fallback-webp")) is not None:
        opts["fallback"] = ("webp", v)
    if (v := take("--density")) is not None:
        opts["density"] = v
    if "--png" in args:
        args.remove("--png")
    source = take("--from-bundle", str)
    out, frames = args[0], args[1:]
    if source:
        import tempfile
        decoded, manifest = decode_frames(source)
        if any(not i["url"].endswith(".png") for i in manifest["images"]):
            print(f"WARNING: {source} is not a PNG bundle - repacking a lossy source compounds the loss")
        opts.setdefault("fps", manifest["fps"])
        tmp = tempfile.mkdtemp(prefix="lava_repack_")
        frames = []
        for i, frame in enumerate(decoded):
            frames.append(os.path.join(tmp, f"frame_{i:03d}.png"))
            Image.fromarray(frame).save(frames[-1])
    encode(frames, out, **opts)
    decode_check(out, frames)
    if "fallback" in opts:
        decode_check(out, frames, which="fallbackUrl")
