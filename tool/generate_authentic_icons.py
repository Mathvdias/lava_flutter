import os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# Everything is composed on a fixed 720x648 canvas (4x the 180x162 OpenLava size) and only the
# final resize depends on the output size, so LAVA_SCALE=2 yields the 360x324 large-preview variant
# of exactly the same animation.
SCALE = int(os.environ.get("LAVA_SCALE", "1"))
W, H = 180 * SCALE, 162 * SCALE
SS = 4
CANVAS_W = 180 * SS
CANVAS_H = 162 * SS
N_FRAMES = 48

def clean_cutout(img_path, is_flower=False):
    """Cleanly extracts the subject from pure white/near-white backdrop."""
    img = Image.open(img_path).convert('RGB')
    rgb = np.array(img).astype(np.float32)
    h, w = rgb.shape[:2]
    
    mn = rgb.min(axis=2)
    chroma = rgb.max(axis=2) - mn
    # Background candidates: low chroma, high brightness
    bg_cand = (chroma < 18) & (mn > 225)
    
    y_coords = np.arange(h)[:, None]
    # For lower half, ground shadow has low chroma and neutral gray tone
    shadow_chroma_thresh = 26 if is_flower else 18
    is_shadow = (y_coords > h * 0.68) & (chroma < shadow_chroma_thresh) & (mn < 253)
    
    # Flood fill from image boundary seeds
    fill_mask = Image.fromarray(((bg_cand | is_shadow) * 255).astype(np.uint8)).copy()
    seeds = [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1), 
             (w//2, 0), (0, h//2), (w-1, h//2), (w//2, h-1),
             (w//4, 0), (3*w//4, 0), (0, h//4), (w-1, h//4),
             (w//4, h-1), (3*w//4, h-1)]
    for seed in seeds:
        if fill_mask.getpixel(seed) == 255:
            ImageDraw.floodfill(fill_mask, seed, 128)
    bg_total = np.array(fill_mask) == 128
    
    fg = ~bg_total
    # Retain largest connected component for foreground
    fg_img = Image.fromarray((fg * 255).astype(np.uint8)).copy()
    cy, cx = int(h * 0.45), w // 2
    if fg_img.getpixel((cx, cy)) == 255:
        ImageDraw.floodfill(fg_img, (cx, cy), 128)
        clean_fg = np.array(fg_img) == 128
    else:
        clean_fg = fg
        
    # Smooth alpha boundary
    alpha_img = Image.fromarray((clean_fg * 255).astype(np.uint8))
    alpha_blur = alpha_img.filter(ImageFilter.GaussianBlur(1.0))
    alpha = np.array(alpha_blur).astype(np.float32) / 255.0
    # Clean fringe: zero out any faint alpha noise below 0.05
    alpha[alpha < 0.05] = 0.0
    
    # Clean edges: unpremultiply against white backdrop
    out_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    out_rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out_rgba[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    
    result = Image.fromarray(out_rgba)
    bbox = result.getbbox()
    return result.crop(bbox)

def draw_contact_shadow(canvas, cx, base_y, width, height, opacity):
    """Draws a soft, realistic ambient occlusion contact shadow."""
    sw, sh = int(width * 1.5), int(height * 2.2)
    shadow_img = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow_img)
    
    # Dual-layer contact shadow: tight dark core + diffuse ambient spread
    # Core contact
    d.ellipse([sw//2 - width//2, sh//2 - height//2, sw//2 + width//2, sh//2 + height//2],
              fill=(15, 18, 25, int(210 * opacity)))
    # Ambient falloff
    d.ellipse([sw//2 - int(width*0.8), sh//2 - int(height*0.8), sw//2 + int(width*0.8), sh//2 + int(height*0.8)],
              fill=(20, 22, 30, int(85 * opacity)))
    
    blurred = shadow_img.filter(ImageFilter.GaussianBlur(height * 0.45))
    canvas.alpha_composite(blurred, (int(cx - sw//2), int(base_y - sh//2)))

def animate_macintosh(src_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cutout = clean_cutout(src_path, is_flower=False)
    
    # Sizing matched to Airbnb icons: ~95px height on 162 canvas -> 380px at 4x SS
    target_h = 380
    scale = target_h / cutout.height
    target_w = int(cutout.width * scale)
    scaled = cutout.resize((target_w, target_h), Image.LANCZOS)
    
    base_x = (CANVAS_W - target_w) // 2
    base_y = (CANVAS_H - target_h) // 2 + 10
    
    # Scaled screen coordinates (cutout had screen at 274..532, 173..460)
    sx0 = int(274 * scale)
    sx1 = int(532 * scale)
    sy0 = int(173 * scale)
    sy1 = int(460 * scale)
    sw = sx1 - sx0
    sh = sy1 - sy0
    
    # True scaled eye coordinates on 3D CRT screen
    lx0, lx1 = 175, 189
    ly0, ly1 = 141, 157
    rx0, rx1 = 215, 229
    ry0, ry1 = 131, 145
    
    # Precompute clean inpainted eye patches for blinking
    scaled_arr = np.array(scaled).copy()
    left_bg = scaled_arr[ly0-3:ly0, lx0:lx1, :3].mean(axis=(0,1)).astype(np.uint8)
    right_bg = scaled_arr[ry0-3:ry0, rx0:rx1, :3].mean(axis=(0,1)).astype(np.uint8)
    
    # Left eye closed
    left_closed_arr = scaled_arr[ly0:ly1, lx0:lx1].copy()
    dark_l = left_closed_arr[..., 0] < 205
    left_closed_arr[dark_l, :3] = left_bg
    left_closed_img = Image.fromarray(left_closed_arr)
    ld = ImageDraw.Draw(left_closed_img)
    mid_ly = (ly1 - ly0) // 2
    ld.line([(1, mid_ly + 2), (lx1 - lx0 - 1, mid_ly - 1)], fill=(35, 75, 70, 255), width=2)
    
    # Right eye closed
    right_closed_arr = scaled_arr[ry0:ry1, rx0:rx1].copy()
    dark_r = right_closed_arr[..., 0] < 205
    right_closed_arr[dark_r, :3] = right_bg
    right_closed_img = Image.fromarray(right_closed_arr)
    rd = ImageDraw.Draw(right_closed_img)
    mid_ry = (ry1 - ry0) // 2
    rd.line([(1, mid_ry + 1), (rx1 - rx0 - 1, mid_ry - 1)], fill=(35, 75, 70, 255), width=2)
    
    frames = []
    
    for i in range(N_FRAMES):
        t = i / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        # 1. Physics / Tactile Float & Settle
        # Smooth hover-bob: rises slightly (frames 12-32), then touches back down
        bob_phase = 2 * math.pi * t
        dy = -int(14 * (1 - math.cos(bob_phase)) / 2) # max 7px rise at 4x (1.75px at 1x)
        yaw_deg = 1.0 * math.sin(bob_phase)
        
        # Ground contact shadow reacts to height
        shadow_w = int(target_w * 0.76)
        shadow_h = 24
        shadow_op = 0.56 - 0.14 * (-dy / 14.0)
        shadow_cx = CANVAS_W // 2
        shadow_base = base_y + target_h + 2
        draw_contact_shadow(canvas, shadow_cx, shadow_base, shadow_w, shadow_h, shadow_op)
        
        # 2. Render Macintosh body with expressive Happy Mac face
        body = scaled.copy()
        
        # Determine blink state:
        # Blink 1 at frames 12..15 (frame 13, 14 fully closed; 12, 15 half)
        # Blink 2 (double blink) at frames 27..29 (frame 28 fully closed)
        blink_closed = (i in (13, 14, 28))
        blink_half = (i in (12, 15, 27, 29))
        
        if blink_closed:
            body.paste(left_closed_img, (lx0, ly0))
            body.paste(right_closed_img, (rx0, ry0))
        elif blink_half:
            # Blend 50% between open and closed
            blended_l = Image.blend(scaled.crop((lx0, ly0, lx1, ly1)), left_closed_img, 0.55)
            blended_r = Image.blend(scaled.crop((rx0, ry0, rx1, ry1)), right_closed_img, 0.55)
            body.paste(blended_l, (lx0, ly0))
            body.paste(blended_r, (rx0, ry0))
            
        # Joyful cheeks blush at frames 32..44 with authentic 3D isometric perspective
        if 32 <= i <= 44:
            blush_p = math.sin((i - 32) / 12.0 * math.pi)
            blush_layer = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
            bd = ImageDraw.Draw(blush_layer)
            
            # Cheeks centered along the screen's 3D isometric tilt:
            # Left cheek: (172, 170), Right cheek: (231, 153)
            # Semi-axes: R_u = 9.0 (along screen plane), R_v = 5.0 (vertical)
            # Screen isometric slope = -0.29
            R_u, R_v = 9.0, 5.0
            iso_slope = -0.29
            for cx, cy in [(172, 170), (231, 153)]:
                for r in range(int(R_u), 0, -1):
                    frac = r / float(R_u)
                    poly = []
                    for deg in range(0, 360, 15):
                        rad = np.radians(deg)
                        u = np.cos(rad) * r
                        v = np.sin(rad) * (R_v * (r / float(R_u)))
                        px = cx + u
                        py = cy + u * iso_slope + v
                        poly.append((px, py))
                    alpha = int(160 * blush_p * (1.0 - frac**1.4))
                    bd.polygon(poly, fill=(255, 125, 155, alpha))
                    
            blush_layer = blush_layer.filter(ImageFilter.GaussianBlur(1.6))
            body.alpha_composite(blush_layer)
            
        # CRT phosphor breathing pulse
        pulse = 1.0 + 0.04 * math.sin(4 * math.pi * t)
        
        # Soft CRT scanline beam sweeping down screen
        scan_y = sy0 + int(sh * ((t * 1.5) % 1.0))
        scan_overlay = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scan_overlay)
        sd.rectangle([sx0, max(sy0, scan_y - 8), sx1, min(sy1, scan_y + 8)],
                     fill=(210, 255, 245, 38))
        scan_overlay = scan_overlay.filter(ImageFilter.GaussianBlur(1.5))
        body.alpha_composite(scan_overlay)
        
        # 3. Composite body onto canvas with subtle yaw micro-tilt
        if abs(yaw_deg) > 0.05:
            rotated = body.rotate(yaw_deg, resample=Image.BICUBIC, expand=True)
            rx = base_x - (rotated.width - target_w) // 2
            ry = base_y + dy - (rotated.height - target_h) // 2
            canvas.alpha_composite(rotated, (rx, ry))
        else:
            canvas.alpha_composite(body, (base_x, base_y + dy))
            
        # Downsample 4x -> 180x162 with Lanczos anti-aliasing
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        frame_file = os.path.join(out_dir, f"frame_{i:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/tmp/macintosh_animated.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
    print(f"Macintosh frames generated successfully: {N_FRAMES} frames")

def animate_sunflower(src_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cutout = clean_cutout(src_path, is_flower=True)
    
    # Sizing matched to Airbnb icons: ~105px height on 162 canvas -> 420px at 4x SS
    target_h = 420
    scale = target_h / cutout.height
    target_w = int(cutout.width * scale)
    scaled = cutout.resize((target_w, target_h), Image.LANCZOS)
    
    base_x = (CANVAS_W - target_w) // 2
    base_y = (CANVAS_H - target_h) // 2 + 10
    
    arr = np.array(scaled).astype(np.float32)
    h, w = arr.shape[:2]
    
    # Golden pollen particle system
    np.random.seed(42)
    n_particles = 14
    pollen_tracks = []
    for _ in range(n_particles):
        pollen_tracks.append({
            'ox': w * (0.42 + 0.16 * np.random.rand()),
            'oy': h * (0.24 + 0.12 * np.random.rand()),
            'speed_y': 0.7 + 0.5 * np.random.rand(),
            'drift_x': (np.random.rand() - 0.5) * 1.4,
            'phase': np.random.rand(),
            'size': 2.0 + np.random.rand() * 2.5,
        })
        
    frames = []
    
    for i in range(N_FRAMES):
        t = i / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        # Organic wind sway phase
        wind_phase = 2 * math.pi * t
        sway_angle = math.sin(wind_phase)
        
        # 1. Contact shadow beneath terracotta pot
        shadow_w = int(target_w * 0.55)
        shadow_h = 20
        shadow_op = 0.58 + 0.05 * math.sin(2 * wind_phase)
        shadow_cx = CANVAS_W // 2
        shadow_base = base_y + target_h + 1
        draw_contact_shadow(canvas, shadow_cx, shadow_base, shadow_w, shadow_h, shadow_op)
        
        # 2. Smooth non-linear organic stem flex
        # Row-by-row horizontal displacement: 0 at pot bottom, ramping smoothly to top
        swayed_arr = np.zeros_like(arr)
        max_shift = 15.0 * sway_angle # ~3.75px at 1x
        
        for y in range(h):
            # Height factor: 0 at base, 1 at top
            factor = max(0.0, (h - y) / float(h))
            # Terracotta pot is in bottom 30% -> stays perfectly still
            if factor < 0.30:
                row_shift = 0.0
            else:
                row_shift = max_shift * ((factor - 0.30) / 0.70) ** 1.35
                
            shift_int = int(round(row_shift))
            
            if shift_int == 0:
                swayed_arr[y] = arr[y]
            elif shift_int > 0:
                swayed_arr[y, shift_int:] = arr[y, :-shift_int]
            else:
                swayed_arr[y, :shift_int] = arr[y, -shift_int:]
                
        swayed_img = Image.fromarray(swayed_arr.astype(np.uint8))
        
        # 3. Drifting golden pollen motes
        pollen_layer = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pollen_layer)
        
        for p in pollen_tracks:
            age = (t + p['phase']) % 1.0
            # Follow head sway + drift upward
            px = p['ox'] + max_shift * 0.85 + p['drift_x'] * age * 40 + 6 * math.sin(2 * math.pi * age + p['phase'])
            py = p['oy'] - p['speed_y'] * age * 90
            alpha = int(240 * math.sin(age * math.pi) ** 1.4)
            if alpha > 12:
                ps = p['size']
                pd.ellipse([px - ps, py - ps, px + ps, py + ps],
                           fill=(255, 220, 90, alpha))
                pd.ellipse([px - ps*0.5, py - ps*0.5, px + ps*0.5, py + ps*0.5],
                           fill=(255, 255, 225, alpha))
                           
        pollen_layer = pollen_layer.filter(ImageFilter.GaussianBlur(0.8))
        swayed_img.alpha_composite(pollen_layer)
        
        canvas.alpha_composite(swayed_img, (base_x, base_y))
        
        # Downsample 4x -> 180x162 with Lanczos anti-aliasing
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        frame_file = os.path.join(out_dir, f"frame_{i:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/tmp/sunflower_animated.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
    print(f"Sunflower frames generated successfully: {N_FRAMES} frames")

def animate_lavalamp(src_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    clean = Image.open(src_path).convert('RGBA')
    
    target_h = 450
    scale = target_h / clean.height
    target_w = int(clean.width * scale)
    scaled = clean.resize((target_w, target_h), Image.LANCZOS)
    
    base_x = (CANVAS_W - target_w) // 2
    base_y = (CANVAS_H - target_h) // 2 + 10
    
    # Rising bubbles particle system
    bubbles = [
        {'ox': target_w * 0.50, 'drift_x': 0.0, 'speed_y': 0.85, 'phase': 0.0, 'rx': 16, 'ry': 24, 'is_main': True},
        {'ox': target_w * 0.58, 'drift_x': 4.0, 'speed_y': 1.10, 'phase': 0.35, 'rx': 8, 'ry': 10, 'is_main': False},
        {'ox': target_w * 0.42, 'drift_x': -3.0, 'speed_y': 0.95, 'phase': 0.65, 'rx': 10, 'ry': 12, 'is_main': False},
        {'ox': target_w * 0.54, 'drift_x': 2.0, 'speed_y': 1.25, 'phase': 0.85, 'rx': 6, 'ry': 7, 'is_main': False},
    ]
    
    frames = []
    for i in range(N_FRAMES):
        t = i / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        # 1. Ground contact shadow
        shadow_w = int(target_w * 0.85)
        shadow_h = 20
        shadow_op = 0.58 + 0.04 * math.sin(2 * math.pi * t)
        shadow_cx = CANVAS_W // 2
        shadow_base = base_y + target_h - 2
        draw_contact_shadow(canvas, shadow_cx, shadow_base, shadow_w, shadow_h, shadow_op)
        
        # 2. Base lamp body
        body = scaled.copy()
        
        # 3. Animated lava fluid morphing
        lava_layer = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lava_layer)
        
        # Warm internal bulb pulse
        bulb_p = 1.0 + 0.12 * math.sin(2 * math.pi * t)
        bulb_y = int(target_h * 0.66)
        bulb_cx = target_w // 2
        
        ld.ellipse([bulb_cx - int(35*bulb_p), bulb_y - 20, bulb_cx + int(35*bulb_p), bulb_y + 20],
                   fill=(255, 180, 40, int(90 * bulb_p)))
        ld.ellipse([bulb_cx - int(20*bulb_p), bulb_y - 12, bulb_cx + int(20*bulb_p), bulb_y + 12],
                   fill=(255, 225, 90, int(130 * bulb_p)))
                   
        # Drifting rising/falling molten blobs
        for b in bubbles:
            age = (t + b['phase']) % 1.0
            y_span = (target_h * 0.64) - (target_h * 0.24)
            if b['is_main']:
                cur_y = target_h * 0.52 - math.sin(2 * math.pi * age) * (y_span * 0.28)
                stretch = 1.0 + 0.30 * math.sin(2 * math.pi * age)
                rx = int(b['rx'] / math.sqrt(stretch))
                ry = int(b['ry'] * stretch)
                cx_blob = b['ox'] + 3 * math.sin(2 * math.pi * age)
            else:
                cur_y = target_h * 0.64 - (age * y_span)
                stretch = 1.0 + 0.15 * math.sin(4 * math.pi * age)
                rx = int(b['rx'])
                ry = int(b['ry'] * stretch)
                cx_blob = b['ox'] + b['drift_x'] * math.sin(2 * math.pi * age)
                
            alpha = int(220 * math.sin(age * math.pi) ** 0.8) if not b['is_main'] else 220
            ld.ellipse([cx_blob - rx*1.5, cur_y - ry*1.5, cx_blob + rx*1.5, cur_y + ry*1.5],
                       fill=(255, 110, 20, int(alpha * 0.45)))
            ld.ellipse([cx_blob - rx, cur_y - ry, cx_blob + rx, cur_y + ry],
                       fill=(255, 165, 30, int(alpha * 0.85)))
            ld.ellipse([cx_blob - rx*0.5, cur_y - ry*0.5, cx_blob + rx*0.5, cur_y + ry*0.5],
                       fill=(255, 235, 110, alpha))
                       
        lava_layer = lava_layer.filter(ImageFilter.GaussianBlur(1.8))
        
        # Specular glass beam passing down
        beam_y = int(target_h * (0.20 + 0.46 * ((t * 1.3) % 1.0)))
        ld.rectangle([int(target_w*0.35), beam_y - 6, int(target_w*0.65), beam_y + 6],
                     fill=(255, 255, 255, 35))
                     
        body.alpha_composite(lava_layer)
        canvas.alpha_composite(body, (base_x, base_y))
        
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        f_arr = np.array(final_frame)
        f_arr[f_arr[..., 3] < 8] = 0
        final_frame = Image.fromarray(f_arr)
        
        frame_file = os.path.join(out_dir, f"frame_{i:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/tmp/lavalamp_animated.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
    print(f"Lava Lamp frames generated successfully: {N_FRAMES} frames")

def animate_campfire(src_path, out_dir):
    # Load base without white smoke
    base = Image.open(src_path)
    
    # Target sizing: fit comfortably within 720x648 with ample margins
    target_w = 440
    scale = target_w / base.width
    target_h = int(base.height * scale)
    scaled = base.resize((target_w, target_h), Image.LANCZOS)
    
    base_x = (CANVAS_W - target_w) // 2
    base_y = (CANVAS_H - target_h) // 2 + 10
    
    # Separate fire from logs/stones
    # In scaled image:
    arr = np.array(scaled).astype(np.float32)
    h, w = arr.shape[:2]
    
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    
    # Fire region: upper central area where color is bright orange/yellow
    # Fire pixels: r > 200, g > 100, b < 100 or very bright core
    y_grid, x_grid = np.indices((h, w))
    fire_y = y_grid < h * 0.65
    fire_cand = fire_y & (r > 190) & (g > 90) & (b < 120) & (a > 30)
    # Bright core
    core_cand = fire_y & (r > 230) & (g > 200) & (b > 120) & (a > 30)
    is_fire = fire_cand | core_cand
    
    # Charcoal embers region: in the bottom center between logs (y: 0.50 to 0.78, x: 0.25 to 0.75)
    ember_y = (y_grid > h * 0.48) & (y_grid < h * 0.80) & (abs(x_grid - w/2) < w * 0.28)
    # Deep red/orange pixels of embers
    is_ember = ember_y & (r > 120) & (g < 90) & (b < 60) & (a > 100)
    
    # Logs and stones body mask
    body_mask = (a > 20) & (~is_fire)
    
    # Prepare base logs/stones image (fire removed or dimmed)
    logs_arr = arr.copy()
    logs_arr[is_fire, 3] = 0
    logs_img = Image.fromarray(logs_arr.astype(np.uint8))
    
    # Prepare fire layer
    fire_arr = np.zeros_like(arr)
    fire_arr[is_fire] = arr[is_fire]
    fire_img = Image.fromarray(fire_arr.astype(np.uint8))
    
    # Fiery ascending sparks (28 sparks)
    random.seed(123)
    sparks = []
    for _ in range(28):
        fx = random.uniform(base_x + target_w*0.35, base_x + target_w*0.65)
        fy = random.uniform(base_y + target_h*0.35, base_y + target_h*0.55)
        rise_speed = random.uniform(2.5, 5.0)
        swirl_amp = random.uniform(8, 22)
        swirl_freq = random.choice([1, 2])
        swirl_phase = random.uniform(0, 2 * math.pi)
        size = random.uniform(2.0, 4.2)
        sparks.append({
            'fx': fx, 'fy': fy, 'rise': rise_speed,
            'swirl_amp': swirl_amp, 'swirl_freq': swirl_freq, 'swirl_phase': swirl_phase,
            'size': size
        })
        
    out_dir = '/tmp/campfire_frames_alive'
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    
    for frame_idx in range(N_FRAMES):
        t = frame_idx / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        # Ground Contact Shadow under river stones
        shadow_img = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_img)
        sw, sh = int(target_w * 0.88), 32
        cx, cy = CANVAS_W // 2, base_y + target_h - 10
        sd.ellipse([cx - sw//2, cy - sh//2, cx + sw//2, cy + sh//2], fill=(16, 18, 22, 170))
        sd.ellipse([cx - int(sw*0.7), cy - int(sh*0.7), cx + int(sw*0.7), cy + int(sh*0.7)], fill=(12, 14, 18, 220))
        shadow_blur = shadow_img.filter(ImageFilter.GaussianBlur(8))
        sh_arr = np.array(shadow_blur)
        sh_arr[sh_arr[..., 3] < 18] = 0
        canvas.alpha_composite(Image.fromarray(sh_arr))
        
        # 1. Composite Base Logs & Stones
        canvas.alpha_composite(logs_img, (base_x, base_y))
        
        # 2. Living Glowing Charcoal Embers (Brasas vivas)
        # Deep thermal pulse with micro-flickers
        ember_pulse = 0.70 + 0.30 * math.sin(2 * math.pi * t) + 0.12 * math.cos(4 * math.pi * t)
        ember_pulse = max(0.4, min(1.2, ember_pulse))
        
        ember_img = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        ed = ImageDraw.Draw(ember_img)
        # Draw hot glowing coal pockets at the center
        coal_centers = [
            (base_x + int(target_w*0.48), base_y + int(target_h*0.68), 32, 14),
            (base_x + int(target_w*0.54), base_y + int(target_h*0.66), 26, 12),
            (base_x + int(target_w*0.42), base_y + int(target_h*0.72), 22, 10),
            (base_x + int(target_w*0.58), base_y + int(target_h*0.70), 20, 10),
            (base_x + int(target_w*0.50), base_y + int(target_h*0.62), 28, 12),
        ]
        for ecx, ecy, erx, ery in coal_centers:
            # Deep red-orange heat
            ed.ellipse([ecx - erx, ecy - ery, ecx + erx, ecy + ery],
                       fill=(255, int(60 * ember_pulse), 0, int(160 * ember_pulse)))
            # Golden core
            ed.ellipse([ecx - int(erx*0.6), ecy - int(ery*0.6), ecx + int(erx*0.6), ecy + int(ery*0.6)],
                       fill=(255, int(150 * ember_pulse), int(20 * ember_pulse), int(220 * ember_pulse)))
            # White-hot spark point
            ed.ellipse([ecx - int(erx*0.25), ecy - int(ery*0.25), ecx + int(erx*0.25), ecy + int(ery*0.25)],
                       fill=(255, 255, int(160 * ember_pulse), int(240 * ember_pulse)))
                       
        ember_blur = ember_img.filter(ImageFilter.GaussianBlur(3.5))
        canvas.alpha_composite(ember_blur)
        
        # 3. Dynamic Living Flame Tongues (Labaredas vivas com deformação orgânica)
        # Apply sinusoidal horizontal shear and vertical licking to the fire layer
        # Flame tip licks upwards and sways
        fire_canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        f_arr = np.array(fire_img).copy()
        
        # Displacement field for organic flickering
        # Top of flames sways more than bottom
        y_norm = 1.0 - (y_grid / float(h)) # 1 at top, 0 at bottom
        sway_factor = np.clip(y_norm * 2.2 - 0.6, 0.0, 1.5)
        
        # Fluid waves: wave1 (main tongue), wave2 (high-freq flicker)
        dx_wave = (12.0 * np.sin(2 * math.pi * t + y_grid * 0.05) +
                   5.0 * np.cos(4 * math.pi * t + y_grid * 0.08)) * sway_factor
        dy_wave = (-6.0 * (0.5 + 0.5 * math.sin(2 * math.pi * t)) - 
                   4.0 * np.sin(4 * math.pi * t + x_grid * 0.04)) * sway_factor
                   
        src_x = np.clip(x_grid - dx_wave, 0, w - 1).astype(np.float32)
        src_y = np.clip(y_grid - dy_wave, 0, h - 1).astype(np.float32)
        
        # Bilinear sampling of the fire layer
        x0 = np.floor(src_x).astype(int)
        x1 = np.clip(x0 + 1, 0, w - 1)
        y0 = np.floor(src_y).astype(int)
        y1 = np.clip(y0 + 1, 0, h - 1)
        
        wx = (src_x - x0)[..., None]
        wy = (src_y - y0)[..., None]
        
        top = (1 - wx) * f_arr[y0, x0] + wx * f_arr[y0, x1]
        bot = (1 - wx) * f_arr[y1, x0] + wx * f_arr[y1, x1]
        warped_fire = (1 - wy) * top + wy * bot
        
        # Boost flame brightness and warmth at the core
        fire_core_boost = np.clip(1.0 + 0.25 * math.sin(2 * math.pi * t), 0.8, 1.3)
        warped_fire[..., 0] = np.clip(warped_fire[..., 0] * fire_core_boost, 0, 255)
        warped_fire[..., 1] = np.clip(warped_fire[..., 1] * (0.9 + 0.2 * math.sin(4 * math.pi * t)), 0, 255)
        
        fire_frame_img = Image.fromarray(warped_fire.astype(np.uint8))
        canvas.alpha_composite(fire_frame_img, (base_x, base_y))
        
        # 4. Volumetric Fire Glow onto Birch Logs and Stones (Warm radial light)
        fire_light = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        fld = ImageDraw.Draw(fire_light)
        fire_cx = base_x + int(target_w * 0.50)
        fire_cy = base_y + int(target_h * 0.46)
        
        light_radius = 120 + 25 * math.sin(2 * math.pi * t)
        light_alpha = int(95 + 35 * math.sin(2 * math.pi * t))
        fld.ellipse([fire_cx - light_radius, fire_cy - light_radius,
                     fire_cx + light_radius, fire_cy + light_radius],
                    fill=(255, 145, 30, light_alpha))
        fld.ellipse([fire_cx - int(light_radius*0.6), fire_cy - int(light_radius*0.6),
                     fire_cx + int(light_radius*0.6), fire_cy + int(light_radius*0.6)],
                    fill=(255, 210, 70, int(light_alpha * 1.3)))
        fld.ellipse([fire_cx - int(light_radius*0.3), fire_cy - int(light_radius*0.3),
                     fire_cx + int(light_radius*0.3), fire_cy + int(light_radius*0.3)],
                    fill=(255, 250, 180, int(light_alpha * 1.6)))
                    
        blurred_light = fire_light.filter(ImageFilter.GaussianBlur(16))
        # Mask fire light strictly to the logs, stones, and fire so it doesn't bleed into transparent background
        c_alpha = np.array(canvas)[..., 3]
        bl_arr = np.array(blurred_light)
        bl_arr[..., 3] = (bl_arr[..., 3].astype(float) * (c_alpha > 30)).astype(np.uint8)
        canvas.alpha_composite(Image.fromarray(bl_arr))
        
        # 5. Ascending Fiery Sparks (Fagulhas vivas subindo)
        spark_layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        spd = ImageDraw.Draw(spark_layer)
        
        for sp in sparks:
            # Rise upwards and loop
            total_rise = CANVAS_H * 0.65
            cur_y = (sp['fy'] - t * total_rise)
            # Wrap around seamlessly
            while cur_y < base_y + target_h * 0.15:
                cur_y += total_rise
            
            # Swirl horizontally
            swirl_x = sp['fx'] + sp['swirl_amp'] * math.sin(2 * math.pi * sp['swirl_freq'] * t + sp['swirl_phase'])
            
            # Fade out at the top
            dist_from_fire = max(0.0, (base_y + target_h * 0.50) - cur_y)
            life = max(0.0, 1.0 - dist_from_fire / (target_h * 0.45))
            alpha_sp = int(255 * life)
            
            if alpha_sp > 20:
                sz = sp['size'] * (0.6 + 0.4 * life)
                # Golden-orange spark
                spd.ellipse([swirl_x - sz, cur_y - sz, swirl_x + sz, cur_y + sz],
                            fill=(255, int(180 * life + 50), 30, alpha_sp))
                # Core white dot
                if sz > 2.0:
                    spd.ellipse([swirl_x - sz*0.4, cur_y - sz*0.4, swirl_x + sz*0.4, cur_y + sz*0.4],
                                fill=(255, 255, 220, alpha_sp))
                                
        spark_blur = spark_layer.filter(ImageFilter.GaussianBlur(0.6))
        canvas.alpha_composite(spark_blur)
        
        # Final resize to 180x162
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        f_arr = np.array(final_frame)
        f_arr[f_arr[..., 3] < 12] = 0
        final_frame = Image.fromarray(f_arr)
        
        frame_file = os.path.join(out_dir, f"frame_{frame_idx:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/tmp/campfire_alive.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
    print("Campfire alive animation complete! Saved /tmp/campfire_alive.gif")

def animate_rocket(src_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cutout = Image.open(src_path).convert('RGBA')
    
    target_h = 390
    scale = target_h / cutout.height
    target_w = int(cutout.width * scale)
    scaled_rocket = cutout.resize((target_w, target_h), Image.LANCZOS)
    
    nozzle_local_x = int(206 * scale)
    nozzle_local_y = int(665 * scale)
    
    base_x = (CANVAS_W - target_w) // 2 + 35
    base_y = (CANVAS_H - target_h) // 2 - 30
    
    nose_local_x = int(642 * scale)
    nose_local_y = int(2 * scale)
    cdx = nozzle_local_x - nose_local_x
    cdy = nozzle_local_y - nose_local_y
    clen = math.hypot(cdx, cdy)
    thrust_dx = cdx / clen
    thrust_dy = cdy / clen
    norm_dx = -thrust_dy
    norm_dy = thrust_dx
    
    sparks = []
    for i in range(28):
        loops = 1 if (i % 3 != 0) else 2
        sparks.append({
            'offset': (i * 0.03571) % 1.0,
            'loops': loops,
            'max_dist': 120 + (i * 13 % 23) * 3.5,
            'spread': ((i % 5) - 2) * 9.0 + ((i * 3 % 7) - 3) * 1.8,
            'phase': (i * 2) % 6,
            'size': 3.0 + (i % 4) * 1.2,
        })
        
    frames = []
    for frame_idx in range(N_FRAMES):
        t = frame_idx / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        surge = math.sin(t * 2 * math.pi) * 3.5 + math.sin(t * 8 * math.pi) * 0.9
        sway = math.cos(t * 2 * math.pi) * 1.4
        
        rx = base_x - int(surge * thrust_dx) + int(sway * norm_dx)
        ry = base_y - int(surge * thrust_dy) + int(sway * norm_dy)
        
        nozzle_cx = rx + nozzle_local_x
        nozzle_cy = ry + nozzle_local_y
        
        flame_pulse = 0.88 + 0.12 * math.sin(t * 4 * math.pi) + 0.05 * math.sin(t * 12 * math.pi)
        outer_len = 135 * flame_pulse
        mid_len = 92 * flame_pulse
        core_len = 54 * flame_pulse
        
        def draw_flame(length, base_w, mid_w, color, blur_r=0):
            layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            p1_dist = length * 0.32
            pts = [
                (nozzle_cx - norm_dx * (base_w / 2), nozzle_cy - norm_dy * (base_w / 2)),
                (nozzle_cx + thrust_dx * p1_dist - norm_dx * (mid_w / 2),
                 nozzle_cy + thrust_dy * p1_dist - norm_dy * (mid_w / 2)),
                (nozzle_cx + thrust_dx * length, nozzle_cy + thrust_dy * length),
                (nozzle_cx + thrust_dx * p1_dist + norm_dx * (mid_w / 2),
                 nozzle_cy + thrust_dy * p1_dist + norm_dy * (mid_w / 2)),
                (nozzle_cx + norm_dx * (base_w / 2), nozzle_cy + norm_dy * (base_w / 2)),
            ]
            d.polygon(pts, fill=color)
            if blur_r > 0:
                layer = layer.filter(ImageFilter.GaussianBlur(blur_r))
            return layer
            
        outer_flame = draw_flame(outer_len, 32, 40, (255, 80, 10, 220), blur_r=2.5)
        canvas.alpha_composite(outer_flame)
        
        mid_flame = draw_flame(mid_len, 22, 26, (255, 185, 25, 245), blur_r=1.5)
        canvas.alpha_composite(mid_flame)
        
        core_flame = draw_flame(core_len, 14, 15, (255, 255, 240, 255), blur_r=0.8)
        canvas.alpha_composite(core_flame)
        
        mach_layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        md = ImageDraw.Draw(mach_layer)
        for diamond_dist, d_w, d_h in [(core_len * 0.42, 9, 15), (core_len * 0.82, 7, 11)]:
            dc_x = nozzle_cx + thrust_dx * diamond_dist
            dc_y = nozzle_cy + thrust_dy * diamond_dist
            d_pts = [
                (dc_x - thrust_dx * (d_h / 2), dc_y - thrust_dy * (d_h / 2)),
                (dc_x + norm_dx * (d_w / 2), dc_y + norm_dy * (d_w / 2)),
                (dc_x + thrust_dx * (d_h / 2), dc_y + thrust_dy * (d_h / 2)),
                (dc_x - norm_dx * (d_w / 2), dc_y - norm_dy * (d_w / 2)),
            ]
            md.polygon(d_pts, fill=(255, 255, 250, int(240 * flame_pulse)))
        canvas.alpha_composite(mach_layer.filter(ImageFilter.GaussianBlur(0.8)))
        
        body = scaled_rocket.copy()
        glint_layer = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        gld = ImageDraw.Draw(glint_layer)
        glint_prog = (t * 2.0) % 1.0
        glint_x = int(target_w * 0.58 + 28 * math.sin(glint_prog * 2 * math.pi))
        glint_y = int(target_h * 0.32 + 18 * math.cos(glint_prog * 2 * math.pi))
        gld.ellipse([glint_x - 14, glint_y - 8, glint_x + 14, glint_y + 8],
                    fill=(255, 255, 255, 32))
        body.alpha_composite(glint_layer.filter(ImageFilter.GaussianBlur(2.0)))
        
        canvas.alpha_composite(body, (rx, ry))
        
        bounce_layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bounce_layer)
        bd.ellipse([nozzle_cx - 36, nozzle_cy - 42, nozzle_cx + 36, nozzle_cy + 22],
                   fill=(255, 145, 25, int(75 * flame_pulse)))
        bounce_mask = Image.new('L', (CANVAS_W, CANVAS_H), 0)
        bounce_mask.paste(body.split()[3], (rx, ry))
        b_blurred = bounce_layer.filter(ImageFilter.GaussianBlur(7.0))
        b_arr = np.array(b_blurred)
        m_arr = np.array(bounce_mask).astype(float) / 255.0
        b_arr[..., 3] = np.clip(b_arr[..., 3].astype(float) * m_arr, 0, 255).astype(np.uint8)
        canvas.alpha_composite(Image.fromarray(b_arr))
        
        throat_layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        td = ImageDraw.Draw(throat_layer)
        td.ellipse([nozzle_cx - 8, nozzle_cy - 7, nozzle_cx + 8, nozzle_cy + 7],
                   fill=(255, 255, 230, int(220 * flame_pulse)))
        canvas.alpha_composite(throat_layer.filter(ImageFilter.GaussianBlur(1.5)))
        
        spark_layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spark_layer)
        for spk in sparks:
            prog = (t * spk['loops'] + spk['offset']) % 1.0
            dist = prog * spk['max_dist']
            lateral = spk['spread'] * math.sin(prog * math.pi) * (1.0 + 0.22 * math.sin(t * 8 * math.pi + spk['phase']))
            sx = nozzle_cx + thrust_dx * dist + norm_dx * lateral
            sy = nozzle_cy + thrust_dy * dist + norm_dy * lateral
            if prog < 0.20:
                r, g, b = 255, 255, 220
                alpha = int(255 * (1.0 - prog * 0.15))
            elif prog < 0.58:
                p_local = (prog - 0.20) / 0.38
                r = 255
                g = int(245 * (1.0 - p_local) + 115 * p_local)
                b = int(185 * (1.0 - p_local) + 10 * p_local)
                alpha = int(245 * (1.0 - p_local * 0.35))
            else:
                p_local = (prog - 0.58) / 0.42
                r = int(255 * (1.0 - p_local * 0.25))
                g = int(105 * (1.0 - p_local * 0.85))
                b = int(10 * (1.0 - p_local))
                alpha = int(170 * (1.0 - p_local))
            cur_sz = max(1.2, spk['size'] * (1.0 - prog * 0.55))
            tail_len = cur_sz * 2.2
            tx = sx - thrust_dx * tail_len
            ty = sy - thrust_dy * tail_len
            sd.line([(tx, ty), (sx, sy)], fill=(r, g, b, alpha), width=int(max(1, cur_sz * 0.8)))
            sd.ellipse([sx - cur_sz/2, sy - cur_sz/2, sx + cur_sz/2, sy + cur_sz/2], fill=(r, g, b, alpha))
            
        canvas.alpha_composite(spark_layer)
        
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        f_arr = np.array(final_frame)
        f_arr[f_arr[..., 3] < 12] = 0
        final_frame = Image.fromarray(f_arr)
        
        frame_file = os.path.join(out_dir, f"frame_{frame_idx:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/tmp/rocket_animated.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
    print(f"Rocket frames generated successfully: {N_FRAMES} frames")

def animate_senna(src_path, out_dir):
    cutout = Image.open(src_path)
    
    # Target size: fit with generous breathing room
    target_h = 350
    scale = target_h / cutout.height
    target_w = int(cutout.width * scale)
    scaled = cutout.resize((target_w, target_h), Image.LANCZOS)
    
    base_x = (CANVAS_W - target_w) // 2
    base_y = (CANVAS_H - target_h) // 2 - 8
    
    out_dir = '/tmp/senna_frames_clean'
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    
    for frame_idx in range(N_FRAMES):
        t = frame_idx / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        phase = 2 * math.pi * t
        dy = -int(12 * (1 - math.cos(phase)) / 2) # max 6px rise at 4x (1.5px at 1x)
        
        # 3D perspective rotation angles
        yaw_deg = 8.0 * math.sin(phase)
        pitch_deg = 2.4 * math.cos(phase)
        roll_deg = -1.6 * math.sin(phase)
        
        # 1. Ground Contact Shadow
        shadow_w = int(target_w * 0.72)
        shadow_h = 24
        shadow_op = 0.54 - 0.12 * (-dy / 12.0)
        shadow_cx = CANVAS_W // 2
        shadow_cy = base_y + target_h + 18
        
        shadow_img = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_img)
        sd.ellipse([shadow_cx - shadow_w//2, shadow_cy - shadow_h//2,
                    shadow_cx + shadow_w//2, shadow_cy + shadow_h//2],
                   fill=(18, 22, 28, int(180 * shadow_op)))
        sd.ellipse([shadow_cx - int(shadow_w*0.75), shadow_cy - int(shadow_h*0.75),
                    shadow_cx + int(shadow_w*0.75), shadow_cy + int(shadow_h*0.75)],
                   fill=(12, 15, 20, int(230 * shadow_op)))
        shadow_blur = shadow_img.filter(ImageFilter.GaussianBlur(8))
        sh_arr = np.array(shadow_blur)
        sh_arr[sh_arr[..., 3] < 20] = 0
        canvas.alpha_composite(Image.fromarray(sh_arr))
        
        # 2. 3D Perspective Rotation of Helmet (proportional scaling and rotation)
        cos_yaw = math.cos(math.radians(yaw_deg))
        cur_w = int(target_w * (0.94 + 0.06 * cos_yaw))
        cur_h = int(target_h * (0.98 + 0.02 * math.cos(math.radians(pitch_deg))))
        
        body_scaled = scaled.resize((cur_w, cur_h), Image.LANCZOS)
        rotated_body = body_scaled.rotate(roll_deg + yaw_deg * 0.35, resample=Image.BICUBIC, expand=True)
        
        body_x = (CANVAS_W - rotated_body.width) // 2
        body_y = base_y + dy + (target_h - rotated_body.height) // 2
        canvas.alpha_composite(rotated_body, (body_x, body_y))
        
        # 3. Dynamic Specular Lighting Sweep ("Jogo de Luz e Brilho")
        light_phase = phase
        light_cx = body_x + rotated_body.width * (0.42 + 0.22 * math.sin(light_phase))
        light_cy = body_y + rotated_body.height * (0.26 + 0.05 * math.cos(light_phase))
        
        spec_layer = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        spec_draw = ImageDraw.Draw(spec_layer)
        
        # A. Dome Specular Highlight (sunlight gliding on yellow lacquer)
        glint_w = 46 + 12 * math.cos(light_phase)
        glint_h = 22 + 6 * math.sin(light_phase)
        spec_draw.ellipse([light_cx - glint_w/2, light_cy - glint_h/2,
                           light_cx + glint_w/2, light_cy + glint_h/2],
                          fill=(255, 255, 235, 140))
        spec_draw.ellipse([light_cx - glint_w*0.5/2, light_cy - glint_h*0.5/2,
                           light_cx + glint_w*0.5/2, light_cy + glint_h*0.5/2],
                          fill=(255, 255, 255, 220))
        
        # B. Visor Metallic Streak (gliding on curved tinted visor)
        v_light_x = body_x + rotated_body.width * (0.35 + 0.25 * math.sin(light_phase - 0.3))
        v_light_y = body_y + rotated_body.height * 0.45
        v_streak_w = 16
        v_streak_h = 65
        v_angle = math.radians(24)
        dx_v = math.sin(v_angle) * (v_streak_h / 2)
        dy_v = math.cos(v_angle) * (v_streak_h / 2)
        spec_draw.line([(v_light_x - dx_v, v_light_y - dy_v),
                        (v_light_x + dx_v, v_light_y + dy_v)],
                       fill=(210, 235, 255, 130), width=int(v_streak_w))
        spec_draw.line([(v_light_x - dx_v*0.6, v_light_y - dy_v*0.6),
                        (v_light_x + dx_v*0.6, v_light_y + dy_v*0.6)],
                       fill=(255, 255, 255, 200), width=int(v_streak_w*0.4))
                       
        # C. Chrome Pivot Screw Starburst Ping
        screw_x = body_x + rotated_body.width * 0.69
        screw_y = body_y + rotated_body.height * 0.49
        dist_to_light = abs(math.sin(light_phase - 0.45))
        if dist_to_light < 0.30:
            intensity = 1.0 - dist_to_light / 0.30
            star_sz = int(18 * intensity)
            spec_draw.line([(screw_x - star_sz, screw_y), (screw_x + star_sz, screw_y)],
                           fill=(255, 255, 255, int(220 * intensity)), width=2)
            spec_draw.line([(screw_x, screw_y - star_sz), (screw_x, screw_y + star_sz)],
                           fill=(255, 255, 255, int(220 * intensity)), width=2)
            d_sz = int(star_sz * 0.6)
            spec_draw.line([(screw_x - d_sz, screw_y - d_sz), (screw_x + d_sz, screw_y + d_sz)],
                           fill=(255, 255, 255, int(150 * intensity)), width=1)
            spec_draw.line([(screw_x - d_sz, screw_y + d_sz), (screw_x + d_sz, screw_y - d_sz)],
                           fill=(255, 255, 255, int(150 * intensity)), width=1)
            spec_draw.ellipse([screw_x - 3, screw_y - 3, screw_x + 3, screw_y + 3],
                              fill=(255, 255, 255, int(255 * intensity)))
                              
        spec_blur = spec_layer.filter(ImageFilter.GaussianBlur(3.0))
        canvas_alpha = np.array(canvas)[..., 3]
        spec_arr = np.array(spec_blur)
        spec_arr[..., 3] = (spec_arr[..., 3].astype(float) * (canvas_alpha > 40)).astype(np.uint8)
        canvas.alpha_composite(Image.fromarray(spec_arr))
        
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        f_arr = np.array(final_frame)
        f_arr[f_arr[..., 3] < 12] = 0
        final_frame = Image.fromarray(f_arr)
        
        frame_file = os.path.join(out_dir, f"frame_{frame_idx:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/Users/matheusdias/.gemini/antigravity-cli/brain/8a22d24e-19f0-4cc2-9411-d668d22ba149/senna_clean.gif",
                   save_all=True, append_images=frames[1:], duration=33, loop=0)
    print("Senna perfect animation complete!")

def animate_christmastree(src_path, out_dir):
    tree = Image.open(src_path)
    tw, th = tree.size
    
    comp_w = tw + 40
    comp_h = th + 90
    composite = Image.new('RGBA', (comp_w, comp_h), (0, 0, 0, 0))
    
    tree_x = 20
    tree_y = 25
    
    # A. 3D Wooden Trunk
    trunk_cx = comp_w // 2
    trunk_top = tree_y + int(th * 0.88)
    trunk_bot = tree_y + th + 35
    trunk_w = 44
    
    trunk_img = Image.new('RGBA', (comp_w, comp_h), (0, 0, 0, 0))
    td = ImageDraw.Draw(trunk_img)
    td.rounded_rectangle([trunk_cx - trunk_w//2, trunk_top, trunk_cx + trunk_w//2, trunk_bot], radius=6, fill=(120, 78, 44, 255))
    td.rounded_rectangle([trunk_cx - trunk_w//2, trunk_top, trunk_cx - trunk_w//2 + 12, trunk_bot], radius=4, fill=(88, 54, 28, 255))
    td.rounded_rectangle([trunk_cx + 4, trunk_top, trunk_cx + trunk_w//2 - 4, trunk_bot], radius=4, fill=(152, 102, 60, 255))
    composite.alpha_composite(trunk_img)
    
    # B. 3D Fluffy Snow Mound Island (Neve ao redor)
    snow_mound = Image.new('RGBA', (comp_w, comp_h), (0, 0, 0, 0))
    smd = ImageDraw.Draw(snow_mound)
    sm_cx = trunk_cx
    sm_cy = trunk_bot + 6
    sm_rx = int(tw * 0.44)
    sm_ry = 28
    
    smd.ellipse([sm_cx - sm_rx - 10, sm_cy - sm_ry + 8, sm_cx + sm_rx + 10, sm_cy + sm_ry + 16], fill=(16, 20, 26, 140))
    smd.ellipse([sm_cx - sm_rx, sm_cy - sm_ry, sm_cx + sm_rx, sm_cy + sm_ry], fill=(210, 225, 240, 255))
    smd.ellipse([sm_cx - int(sm_rx*0.90), sm_cy - int(sm_ry*0.90) - 3, sm_cx + int(sm_rx*0.90), sm_cy + int(sm_ry*0.90) - 3], fill=(235, 243, 252, 255))
    smd.ellipse([sm_cx - int(sm_rx*0.78), sm_cy - int(sm_ry*0.78) - 6, sm_cx + int(sm_rx*0.78), sm_cy + int(sm_ry*0.78) - 6], fill=(255, 255, 255, 255))
    
    drifts = [
        (-sm_rx*0.6, 2, 24, 14), (sm_rx*0.6, 1, 26, 15),
        (-sm_rx*0.25, 6, 28, 16), (sm_rx*0.25, 5, 26, 15),
        (0, 8, 30, 18), (-trunk_w//2 - 4, -4, 14, 10), (trunk_w//2 + 4, -4, 14, 10)
    ]
    for dx, dy, rx, ry in drifts:
        smd.ellipse([sm_cx + dx - rx, sm_cy + dy - ry, sm_cx + dx + rx, sm_cy + dy + ry], fill=(245, 250, 255, 255))
        smd.ellipse([sm_cx + dx - rx*0.7, sm_cy + dy - ry*0.7 - 2, sm_cx + dx + rx*0.7, sm_cy + dy + ry*0.7 - 2], fill=(255, 255, 255, 255))
        
    snow_smooth = snow_mound.filter(ImageFilter.GaussianBlur(1.2))
    composite.alpha_composite(snow_smooth)
    
    # C. Pine tree body (cleanly mask top 160px where old star was)
    t_arr = np.array(tree).copy()
    y_g, x_g = np.indices((th, tw))
    old_star_mask = (y_g < 145) & (abs(x_g - 263) < 65)
    t_arr[old_star_mask, 3] = 0
    tree_no_star = Image.fromarray(t_arr)
    composite.alpha_composite(tree_no_star, (tree_x, tree_y))
    
    # D. Sharp, Authentic 3D Isometric Faceted Golden Star
    star_cx = tree_x + 263
    star_cy = tree_y + 92
    
    star_img = Image.new('RGBA', (comp_w, comp_h), (0, 0, 0, 0))
    std = ImageDraw.Draw(star_img)
    
    R_out_x = 54.0
    R_out_y = 46.0   # Isometric 30-deg vertical foreshortening
    R_in_x = 19.0
    R_in_y = 16.0
    
    angles = [i * math.pi / 5 - math.pi / 2 for i in range(10)]
    outer_pts = [(star_cx + R_out_x * math.cos(angles[i]), star_cy + R_out_y * math.sin(angles[i])) for i in range(0, 10, 2)]
    inner_pts = [(star_cx + R_in_x * math.cos(angles[i]), star_cy + R_in_y * math.sin(angles[i])) for i in range(1, 10, 2)]
    
    lit_gold = (255, 245, 140, 255)
    mid_gold = (248, 202, 50, 255)
    deep_gold = (212, 145, 24, 255)
    
    center = (star_cx, star_cy)
    for i in range(5):
        p_out = outer_pts[i]
        p_in_l = inner_pts[(i - 1) % 5]
        p_in_r = inner_pts[i]
        # Left facet
        std.polygon([center, p_out, p_in_l], fill=lit_gold if i in [0, 4] else mid_gold)
        # Right facet
        std.polygon([center, p_out, p_in_r], fill=mid_gold if i in [0, 4] else deep_gold)
        
    for i in range(5):
        std.line([center, outer_pts[i]], fill=(255, 255, 225, 255), width=2)
        std.line([center, inner_pts[i]], fill=(195, 130, 20, 255), width=1)
        
    # Micro central glint
    std.ellipse([star_cx - 4, star_cy - 4, star_cx + 4, star_cy + 4], fill=(255, 255, 230, 255))
    
    star_smooth = star_img.filter(ImageFilter.GaussianBlur(0.6))
    composite.alpha_composite(star_smooth)
    
    # Crop to clean bounding box
    final_base = composite.crop(composite.getbbox())
    
    target_h = 440
    scale = target_h / final_base.height
    target_w = int(final_base.width * scale)
    scaled_tree = final_base.resize((target_w, target_h), Image.LANCZOS)
    
    base_x = (CANVAS_W - target_w) // 2
    base_y = (CANVAS_H - target_h) // 2 + 10
    
    star_x = base_x + int((star_cx - composite.getbbox()[0]) * scale)
    star_y = base_y + int((star_cy - composite.getbbox()[1]) * scale)
    
    arr = np.array(scaled_tree)
    body = arr[int(target_h*0.14):int(target_h*0.88)]
    r, g, b, a = body[..., 0].astype(int), body[..., 1].astype(int), body[..., 2].astype(int), body[..., 3].astype(int)
    lights_mask = (r > 215) & (g > 180) & (b > 115) & (a > 200)
    coords = np.argwhere(lights_mask)
    clusters = []
    for y, x in coords:
        real_y = y + int(target_h*0.14)
        real_x = x
        found = False
        for i, (cy, cx, cnt) in enumerate(clusters):
            if (real_y - cy)**2 + (real_x - cx)**2 < (12*scale*2)**2:
                clusters[i] = ((cy*cnt + real_y)/(cnt+1), (cx*cnt + real_x)/(cnt+1), cnt+1)
                found = True
                break
        if not found:
            clusters.append((float(real_y), float(real_x), 1))
            
    bulbs = [(base_x + int(cx), base_y + int(cy)) for cy, cx, cnt in clusters if cnt >= 3]
    
    colors = [
        (255, 235, 130), (255, 75, 75), (75, 230, 130),
        (90, 190, 255), (255, 170, 60), (255, 120, 220),
    ]
    random.seed(42)
    bulb_props = []
    for i, (bx, by) in enumerate(bulbs):
        col = colors[i % len(colors)]
        phase = random.uniform(0, 2 * math.pi)
        freq = random.choice([1, 2, 3])
        bulb_props.append((bx, by, col, phase, freq))
        
    # SLOW GENTLE SNOWFLAKES ("floquinhos de neve devagar")
    snowflakes = []
    random.seed(99)
    for i in range(45):
        is_fg = (i >= 20)
        x0 = random.uniform(30, CANVAS_W - 30)
        fall_total = random.uniform(36, 64)
        y0 = random.uniform(20, CANVAS_H - 20)
        sway_amp = random.uniform(6, 14) if is_fg else random.uniform(3, 7)
        sway_freq = random.choice([1, 2])
        sway_phase = random.uniform(0, 2 * math.pi)
        size = random.uniform(2.5, 4.5) if is_fg else random.uniform(1.8, 2.8)
        snowflakes.append({
            'x0': x0, 'y0': y0, 'fall_total': fall_total,
            'sway_amp': sway_amp, 'sway_freq': sway_freq, 'sway_phase': sway_phase,
            'size': size, 'is_fg': is_fg
        })
        
    out_dir = '/tmp/tree_frames_perfect'
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    
    for frame_idx in range(N_FRAMES):
        t = frame_idx / float(N_FRAMES)
        canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        
        # 1. Background snowflakes
        bg_snow = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_snow)
        for sf in snowflakes:
            if not sf['is_fg']:
                cy = (sf['y0'] + t * sf['fall_total']) % (CANVAS_H - 40) + 20
                cx = sf['x0'] + sf['sway_amp'] * math.sin(2 * math.pi * sf['sway_freq'] * t + sf['sway_phase'])
                r = sf['size']
                bg_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(225, 238, 255, 210))
        canvas.alpha_composite(bg_snow)
        
        # 2. Tree with Trunk and Snow Base
        canvas.alpha_composite(scaled_tree, (base_x, base_y))
        
        # 3. Fairy Lights (Pisca-Piscas)
        lights_img = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lights_img)
        for bx, by, col, phase, freq in bulb_props:
            intensity = 0.5 + 0.5 * math.sin(2 * math.pi * freq * t + phase)
            core_r = 1.6 + 1.2 * intensity
            cr, cg, cb = col
            ld.ellipse([bx - core_r, by - core_r, bx + core_r, by + core_r], fill=(cr, cg, cb, 255))
            if intensity > 0.4:
                glow_r = 3.5 + 4.0 * intensity
                ld.ellipse([bx - glow_r, by - glow_r, bx + glow_r, by + glow_r], fill=(cr, cg, cb, int(85 * intensity)))
        lights_blur = lights_img.filter(ImageFilter.GaussianBlur(1.0))
        canvas.alpha_composite(lights_blur)
        
        # 4. Golden Star Halo
        star_glow = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        sgd = ImageDraw.Draw(star_glow)
        star_pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t)
        aura_r = 20 + 8 * star_pulse
        sgd.ellipse([star_x - aura_r, star_y - aura_r, star_x + aura_r, star_y + aura_r], fill=(255, 215, 60, int(85 * (0.8 + 0.2*star_pulse))))
        blurred_star = star_glow.filter(ImageFilter.GaussianBlur(3.0))
        st_arr = np.array(blurred_star)
        st_arr[st_arr[..., 3] < 16] = 0
        canvas.alpha_composite(Image.fromarray(st_arr))
        
        # 5. Foreground snowflakes
        fg_snow = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        fg_draw = ImageDraw.Draw(fg_snow)
        for sf in snowflakes:
            if sf['is_fg']:
                cy = (sf['y0'] + t * sf['fall_total']) % (CANVAS_H - 40) + 20
                cx = sf['x0'] + sf['sway_amp'] * math.sin(2 * math.pi * sf['sway_freq'] * t + sf['sway_phase'])
                r = sf['size']
                fg_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))
        canvas.alpha_composite(fg_snow)
        
        final_frame = canvas.resize((W, H), Image.LANCZOS)
        f_arr = np.array(final_frame)
        f_arr[f_arr[..., 3] < 12] = 0
        final_frame = Image.fromarray(f_arr)
        
        frame_file = os.path.join(out_dir, f"frame_{frame_idx:03d}.png")
        final_frame.save(frame_file)
        frames.append(final_frame)
        
    frames[0].save("/Users/matheusdias/.gemini/antigravity-cli/brain/8a22d24e-19f0-4cc2-9411-d668d22ba149/christmas_tree_clean.gif",
                   save_all=True, append_images=frames[1:], duration=33, loop=0)
    print("Christmas tree perfect animation complete!")

ANIMATIONS = {
    "macintosh": animate_macintosh,
    "sunflower": animate_sunflower,
    "lavalamp": animate_lavalamp,
    "rocket": animate_rocket,
}

if __name__ == '__main__':
    # generate_authentic_icons.py <macintosh|sunflower|lavalamp|rocket> <still> <frames_dir>
    # (stills are kept in tool/stills/; the campfire, helmet and Christmas tree moved to
    # relight_icon.py and sdf_scenes.py)
    ANIMATIONS[sys.argv[1]](sys.argv[2], sys.argv[3])
