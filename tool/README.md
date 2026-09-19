# OpenLava asset pipeline

How the built-in demo bundles were produced, so new icons can be added with the same look as the
Airbnb samples. There are three ways to get frames, all ending in `openlava_encode.py`:

| Route | Script | Use it when | Built with it |
| --- | --- | --- | --- |
| Still + motion | `animate_icon.py` | one rendered still, secondary motion is enough | Macintosh, sunflower |
| Lit / unlit pair | `relight_icon.py` | the icon has a light source that must light the rest of it, a part with two states (the DRS flap), or something simulated over one still (steering light, a cloth flag) | campfire, Christmas tree, F1 cars, victory lap |
| Procedural 3D | `sdf_scenes.py` (+ `lava_sdf.py`) | the object has to turn on its own axis | racing helmet |

Sections 1-3 cover the first route; 4 and 5 the other two.

Requirements: `python3` with `Pillow` and `numpy` (`python3 -m pip install --user Pillow numpy`).

## 1. Render the still

Generate a single 3D icon on a flat white background (any image model works). Prompt used:

> Premium 3D icon of *\<subject\>*, isometric perspective, high-resolution octane 3D render.
> Soft ambient light from top-right, gentle drop shadow below, mild edge highlights, semi-matte
> satin surfaces, stylized naturalism, crisp edges with no outlines, harmonious muted colors with
> slight saturation boost. Single centered object filling the frame comfortably within margins,
> no text, no props, pure flat white background #FFFFFF.

For a subject with a small "hero" part (the sunflower head), ask for a close-up in the prompt
("the big round flower head is the hero and fills most of the frame, very short stem, small pot at
the bottom edge"): the OpenLava canvas is only 180×162, so whatever must stay legible has to be
large in the still.

The image model kept adding a keyboard whenever the prompt said "computer"; the Macintosh 128K
silhouette came out right only when described geometrically ("a retro beige plastic box, taller
than wide, with a recessed screen in the upper front and a thin horizontal slot in the lower front,
nothing attached to it").

## 2. Key + animate

```sh
python3 tool/animate_icon.py sunflower flower_raw.png   sunflower_frames
python3 tool/animate_icon.py macintosh mac_raw.png       mac_frames
```

`animate_icon.py` keys out the (off-)white studio background with a border flood fill, drops the
baked-in drop shadow, then renders 48 frames (1.6 s loop at 30 fps) at the OpenLava canvas size
(180×162 @2x, rendered at 4x and downsampled). Every subject gets a pseudo-3D yaw rock
(perspective warp), a hover/bob and a synthetic contact shadow that reacts to the motion; on top
of that each `Subject` subclass adds its own secondary animation:

- `Sunflower`: wind bend (row-wise shear that grows with height above the pot rim, which is
  detected from the bottom up), the petal ring turning a few degrees around the seed centre while
  the centre and its highlight stay put, and pollen motes drifting up;
- `Bonsai` (kept as a reference subject): the same wind bend plus two leaves tumbling down;
- `Macintosh`: the rendered face is erased and a pixel face is drawn per frame (blink, glance
  to the side, smile), plus a phosphor glow pulse and a scanline band sweeping the CRT.

Add a new `Subject` subclass (override `layer()` / `motion()`) and a `KEY_PARAMS` entry for a
new icon. Geometric transforms go through the premultiplied-alpha helpers (`rotate_pm`,
`yaw_rock`): bicubic resampling of straight-alpha RGBA leaves dark fringes on every edge.

## 3. Encode to OpenLava

```sh
python3 tool/openlava_encode.py assets/lava/sunflower --avif 70 --fallback-webp 90 sunflower_frames/frame_*.png
python3 tool/openlava_encode.py assets/lava/senna     --avif 70 --fallback-webp 95 --fps 24 senna_frames/frame_*.png
python3 tool/openlava_encode.py assets/lava/rocket    --from-bundle <lossless rocket bundle> --avif 70 --fallback-webp 90
```

Produces `image_1` (key frame), `image_2` (2048px-wide diff tile atlas, 32px cells) and
`manifest.json` (`{"type":"key"}` + `{"type":"diff","diffs":[[srcImage, srcTile, countX, countY,
dstTile], ...]}` per frame), the layout of the Airbnb samples. Then list the directory under
`flutter.assets` in the host `pubspec.yaml` and map it in `LavaBundle.demoAssetPaths` (or load it
directly with `LavaBundle.openLavaAsset`).

**Packing** follows OpenLava's `Docs/packing.md`. Every tile of every frame gets an id (identical
pixels, same id; colour under alpha 0 is zeroed first). Per frame, fully transparent tiles cost
nothing (the canvas starts cleared), tiles found in the key image are copied from it, tiles already
in the atlas are referenced again - growing the largest rectangle contiguous both in the frame and
in its source - and only tiles never seen before become a new patch; patches are shelf-packed
tallest first. Against one bounding block per frame this stores 20-57 % fewer tiles on the demo
icons (sunflower 690 -> 296, rocket 924 -> 374, helmet 2130 -> 1612), which also shrinks the decoded
atlas (the helmet's went from 12.3 MB to 7.3 MB of texture). `lava_flutter` composes frames 1:1 with
nearest sampling before scaling, so neighbouring atlas tiles cannot bleed and no gutter is needed;
`--gutter 1` restores one for players that blit scaled tiles straight from the atlas.

**Design for tile reuse.** A 180x162 canvas is only 6x6 tiles, so anything that changes every pixel
every frame (a whole-object bob or rock, a continuously varying light) defeats the packer. Loops
that pass through the same pose twice (any sin-driven motion) are stored once; light that takes a
few discrete levels (`Campfire.LIGHT_LEVELS`, `ChristmasTree.BLINK_LEVELS`) lets every tile away
from the emitter repeat; glow tails below visibility are clamped to zero so they do not dirty far
tiles. That is how the Airbnb samples stay near 100 KB.

**Formats.** `--avif Q` writes 4:4:4 AVIF (what Airbnb ships): at the same size as WebP it has a
third of the peak error, and it is the only lossy option that keeps thin saturated lines (the helmet
stripes) because WebP is 4:2:0 only. `--fallback-webp Q` writes a second copy of both images and
lists it as `fallbackUrl` in the manifest; `--webp Q` / `--png` write a single format (`--webp 100`
is lossless). The decode check reports the premultiplied error of every variant: 0 for lossless,
around 0.3-1.2 / 255 on average for the shipped bundles. Repacking with `--from-bundle` must start
from a lossless bundle (the PNG versions are in git history), never from a lossy one.

**Large previews.** `LAVA_SCALE=2` makes every generator (`animate_icon.py`, `relight_icon.py`,
`sdf_scenes.py`, `generate_authentic_icons.py`) render the same animation at 360x324; encode it
next to the standard bundle as `<name>_hd` with `--density 4`. `LavaIcon.demo` switches to it when
the icon is painted well above 180 device pixels and shows the standard bundle while it decodes.

```sh
LAVA_SCALE=2 python3 tool/relight_icon.py campfire tool/stills/campfire_lit.webp tool/stills/campfire_unlit.webp fire_hd
python3 tool/openlava_encode.py assets/lava/campfire_hd --density 4 --avif 58 --fallback-webp 84 fire_hd/frame_*.png
```

The Macintosh, sunflower, lava lamp and rocket come from `generate_authentic_icons.py <name>
tool/stills/<name>.* <frames_dir>` (it composes on a fixed 720x648 canvas, so both sizes are the
same animation).

Who loads what: on the **web** the AVIF is tried first - only the requested file is downloaded, and
because Flutter web's `ImageDecoder` call rejects every still AVIF on Chrome
(flutter/flutter#160600) the loader decodes it through `createImageBitmap` instead. **Native**
platforms load the `fallbackUrl` directly (`LavaBundle.preferFallbackImages`): Android 12-15 decode
AVIF but silently drop its alpha channel, Linux and older Android cannot decode it at all, and
assets are embedded in native apps anyway. A native-only app can delete the `.avif` files.

## 4. Icons that emit light: lit / unlit pair

A still cannot flicker. Ask the image model for the icon twice, pixel-aligned: first with the light
source on, then as an *edit of that same image* with it off ("keep exactly the same composition,
camera and background, pixel-aligned; the fire is out; remove the flame and every bit of warm
glow it cast on the logs, stones and ground; nothing else may change"). `lit - unlit` is then a
real light pass - what the source adds to every surface around it - and the frames are rebuilt as
`unlit + light_pass * intensity(t)`:

```sh
python3 tool/relight_icon.py campfire      tool/stills/campfire_lit.webp      tool/stills/campfire_unlit.webp      fire_frames
python3 tool/relight_icon.py christmastree tool/stills/christmastree_lit.webp tool/stills/christmastree_unlit.webp tree_frames
python3 tool/openlava_encode.py assets/lava/campfire      --avif 65 --fallback-webp 88 fire_frames/frame_*.png
python3 tool/openlava_encode.py assets/lava/christmastree --avif 65 --fallback-webp 88 tree_frames/frame_*.png
```

- `Campfire`: the flame is lifted out of the lit still by colour (a morphological opening drops the
  glowing log ends that hang off it, the pointed tip is kept), then bent row by row, stretched and
  redrawn over the unlit logs; the light pass follows the same flicker in 8 discrete levels,
  bloom feeds the alpha channel so the glow survives on dark backgrounds, sparks rise and fade.
- `ChristmasTree`: the bright cores of the light pass are split into connected components, one
  per bulb, each owning the pool of light around it; pools switch off / half / on in sequence along
  the string and the star breathes. Snow falls in front; the tree itself stands still so its tiles
  repeat (`ROCK_DEGREES` brings the pseudo-3D rock back at the cost of a much larger atlas).

- `F1Car`: the pair is DRS closed / DRS open. **Pick the camera for the part that moves**: from
  the front or from above the flap is a thin strip and an open DRS is a hairline (and an image
  model asked to exaggerate it lifts a whole second wing, endplates and all). From the TV chase
  camera, at wing height, the flap is a tall band and when it lies flat the livery shows through
  the gap - readable at 44 px. Ask for the closed still with "the rear wing clearly built from two
  stacked elements, a thin slot line between them", then for the edit "the upper flap has rotated
  flat, pivoting about its top edge: a thin blade at the top, and through the gap you see the
  engine cover ahead of the wing". The in-between positions squash the closed flap against its top
  edge (the pivot), column by column, over the open still. One story per loop: the flap opens, the
  car gains speed, sparks pour out from under the diffuser towards the camera, the flap closes and
  they die down; the rain light blinks and streaks rush along rays from the vanishing point. Two
  body states, four flap positions and two lamp states keep the car's tiles repeating: 429 atlas
  tiles instead of 1230. `shadow_floor` keys out the baked shadow trapped between the wheels. No
  logos or sponsor decals were asked for in the still.

- `F1Front`: a single still (pass it twice); the only motion is the steering, and it is done
  with light alone: the tread highlight slides towards the steer and the far side of the tyre
  darkens, while the outline stays where it is. Two other routes were tried and dropped. An image
  model asked to steer the wheels invents rims, sidewall lines and new brake ducts, at a different
  angle each time. Warping the tyre silhouette geometrically (it should widen by
  `W cos t + D sin t`) tears against the brake-duct fairing and the wing endplate that partly
  cover it. Five distinct frames in a 72-frame loop keep the bundle tiny. Ask for the still on a
  magenta backdrop (the helmet is white) with "plain smooth matte black slicks: no rim, no
  lettering, no white lines" and a helmet "small compared with the car, about one eighth of its
  width, sitting low behind the halo" - image models give toy drivers huge heads otherwise. The
  magenta key works by hue (`min(R, B) - G`), so shadows cast on the backdrop and enclosed pockets
  go with it and the tyre edges stay intact. The helmet follows a real driver's colours and lion,
  without sponsor logos.

- `SennaFlag`: one still of the car with the driver holding a BARE flagpole ("the pole is
  completely bare: no flag, no cloth, no banner"); the flag is cloth simulated in `flag_layer` and
  drawn under the car layer, so the pole and the glove stay in front. A wave travels from the
  hoist to the fly with growing amplitude (pinned at the pole), a faster ripple rides on it, the
  fly end droops, each strip advances by the cosine of its slope (foreshortening) and folds are
  shaded by their slope against the top-left light - that shading is what makes it read as fabric.
  `brazil_flag()` builds the texture (the motto is left out: not legible at icon size) and it is
  mirrored because we see the reverse of a flag whose hoist is on the right. Anything that can be
  simulated needs no second image - useful whenever image editing is unavailable. Red and white
  livery and yellow helmet with green and blue stripes, no sponsor logos.

Backdrop: white is fine for the campfire (the smooth baked drop shadow is flood-filled away, the
textured stones stop the fill). Anything white at the silhouette (snow) needs a chroma backdrop:
ask for "a perfectly flat uniform pure magenta background #FF00FF (chroma key)"; `key_backdrop`
removes enclosed pockets and despills the outline.

## 5. Icons that turn: procedural 3D

`lava_sdf.py` is a small numpy SDF ray marcher tuned for this look: orthographic three-quarter
camera, soft top-left key light with soft shadows, hemisphere ambient, ambient occlusion, satin
specular, fresnel rim, emissive materials, point lights, bloom and a blurred contact shadow that
fades before the frame edge. A scene is a `Scene` subclass returning `(distance, material)` parts;
materials can be callables of the hit point, so paint jobs (the helmet bands, the visor gasket) are
painted in object space. Every motion is a whole multiple of the loop phase, so loops are seamless.

```sh
python3 tool/sdf_scenes.py senna --still 0.1 preview.png     # look-dev, about 3 s
python3 tool/sdf_scenes.py senna assets/lava/senna           # 72 frames on all cores, about 10 s
python3 tool/openlava_encode.py assets/lava/senna --fps 24 --avif 70 --fallback-webp 95 <frames_dir>/frame_*.png
```

The helmet makes one turn in 72 frames at 24 fps; in the app, `dragToRotate` scrubs those frames, so
dragging spins it by hand. `sdf_scenes.py` also carries fully procedural `campfire` and
`christmastree` scenes (flame as an emissive SDF that lights the logs through a point light, fairy
lights as blinking point lights): they need no image model at all, but the lit / unlit route above
gives far richer materials, so the shipped bundles use that.
