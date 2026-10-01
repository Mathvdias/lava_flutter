"""Decode an OpenLava bundle (manifest + key/diff images) and write an animated GIF."""
import json, math, os, sys
import numpy as np
from PIL import Image

def decode_frames(bundle_dir, which="fallbackUrl"):
    m = json.load(open(os.path.join(bundle_dir, "manifest.json")))
    cell = m.get("cellSize", 32)
    imgs = []
    for i in m["images"]:
        name = i.get(which) or i["url"]
        imgs.append(np.array(Image.open(os.path.join(bundle_dir, name)).convert("RGBA")))
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

def composite_white(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    rgb = rgba[..., :3].astype(np.float32) * a + 255.0 * (1.0 - a)
    return Image.fromarray(rgb.round().astype(np.uint8))

def main(bundle_dir, out_path, step=1, colors=256, scale=1.0):
    frames, m = decode_frames(bundle_dir)
    fps = m.get("fps", 30)
    frames = frames[::step]
    duration_ms = int(round(1000.0 * step / fps / 10.0)) * 10
    pil = [composite_white(f) for f in frames]
    if scale != 1.0:
        size = (int(pil[0].width * scale), int(pil[0].height * scale))
        pil = [p.resize(size, Image.LANCZOS) for p in pil]
    # Shared global palette: quantize a strip of all frames once, then map each frame to it.
    strip = Image.new("RGB", (pil[0].width, pil[0].height * len(pil)))
    for i, p in enumerate(pil):
        strip.paste(p, (0, i * pil[0].height))
    pal = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q = [p.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG) for p in pil]
    q[0].save(out_path, save_all=True, append_images=q[1:], loop=0, duration=duration_ms,
              optimize=True, disposal=1)
    size = os.path.getsize(out_path)
    print(f"{out_path}: {len(q)} frames @ {duration_ms} ms, {pil[0].width}x{pil[0].height}, {size/1024:.0f} KB")
    return size

if __name__ == "__main__":
    bundle, out = sys.argv[1], sys.argv[2]
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    colors = int(sys.argv[4]) if len(sys.argv) > 4 else 256
    scale = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
    main(bundle, out, step, colors, scale)
