# lava_flutter

[![pub package](https://img.shields.io/pub/v/lava_flutter.svg)](https://pub.dev/packages/lava_flutter)
[![CI](https://github.com/Mathvdias/lava_flutter/actions/workflows/ci.yml/badge.svg)](https://github.com/Mathvdias/lava_flutter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Mathvdias/lava_flutter/blob/main/LICENSE)

Tile-based micro-animation engine for Flutter. It plays **OpenLava** bundles -
3D-rendered icons packed as one key frame plus a tile atlas of what changes -
with a native alpha channel, at the display's refresh rate (60/120 fps), with no
video decoder and no per-frame allocation. Icons can tilt under the pointer,
bounce when pressed and be turned by hand.

<p align="center">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/bingo_ball.gif" width="150" alt="Bingo ball">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/dice.gif" width="150" alt="Dice">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/trophy.gif" width="150" alt="Trophy">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/senna.gif" width="150" alt="Racing helmet">
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/pencil.gif" width="150" alt="Pencil">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/premium_badge.gif" width="150" alt="Premium badge">
  <img src="https://raw.githubusercontent.com/Mathvdias/lava_flutter/main/doc/gifs/bingo_cage.gif" width="150" alt="Bingo cage">
</p>

*Rendered from OpenLava bundles of 60-250 KB each. The GIFs above are a lossy
preview; in the app the icons are sharp, alpha-blended and loop seamlessly.*

## Features

- **OpenLava playback**: `manifest.json` + key frame + diff tile atlas, the
  format behind Airbnb's dimensional icons. A 48-frame icon ships in 60-250 KB.
- **Native alpha**: 32-bit RGBA frames blend into any background, light or dark.
- **Zero-allocation paint loop**: the manifest is compiled once into typed-data
  blit plans; each frame is one `drawRawAtlas` call per source image, composed
  1:1 (no tile bleeding, no seams) and cached, so a looping icon stops
  compositing after its first pass.
- **Shared decoding**: a bundle is decoded once per asset path and shared by
  every widget showing it; composed frames are freed when the last one leaves.
- **Playback control**: play, pause, stop, seek, speed, loop bounds
  ("intro, then loop"), and `playOnce` for icons that react to a selection.
- **Interaction**: hover tilt (perspective transform), elastic press bounce
  with haptics, drag to rotate, hover scrubbing.
- **AVIF + WebP**: bundles may carry an AVIF atlas with a WebP `fallbackUrl`;
  the web loads the AVIF, native platforms the fallback.
- Pure Flutter: no platform code, no dependencies beyond the SDK. Runs on
  Android, iOS, web (including WASM), macOS, Windows and Linux.

## Getting started

```yaml
dependencies:
  lava_flutter: ^0.1.0
```

Copy an OpenLava bundle directory into your app and declare it as an asset
(the trailing slash includes every file in it):

```
assets/lava/bingo_ball/
  manifest.json
  image_1.webp   # key frame
  image_2.webp   # tile atlas
```

```yaml
flutter:
  assets:
    - assets/lava/bingo_ball/
```

## Usage

### Show an icon

```dart
import 'package:lava_flutter/lava_flutter.dart';

class BallIcon extends StatefulWidget {
  const BallIcon({super.key});

  @override
  State<BallIcon> createState() => _BallIconState();
}

class _BallIconState extends State<BallIcon> {
  late final Future<LavaBundle> _bundle =
      LavaBundle.openLavaAsset(assetPath: 'assets/lava/bingo_ball');

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<LavaBundle>(
      future: _bundle,
      builder: (context, snapshot) {
        final bundle = snapshot.data;
        if (bundle == null) return const SizedBox(width: 64, height: 64);
        return LavaIcon(bundle: bundle, size: 64);
      },
    );
  }
}
```

`LavaBundle.openLavaAsset` decodes a bundle once per asset path; every
`LavaIcon` pointing at the same bundle shares its textures and composed frames.
Do not dispose these bundles yourself: `LavaBundle.evictOpenLavaCache()`
releases them all (on logout, or when a feature goes away).

`LavaIcon` scales the frame into its box with `fit` and `alignment`, and can
tint it with `color` / `blendMode`, like `Image`.

### Control playback

Give the icon a `LavaController`. The widget configures it from the bundle's
manifest (frame count, fps, loop bounds) as soon as the bundle is on screen.

```dart
final controller = LavaController(
  totalFrames: 48,
  fps: 30,
  loop: true,
  autoPlay: false,
);

LavaIcon(bundle: bundle, controller: controller, size: 64);

controller.play();
controller.pause();
controller.seekToFrame(12);
controller.seekToProgress(0.5);
controller.setSpeed(1.5);
controller.stop();
```

`controller.currentFrameNotifier` and `statusNotifier` are `ValueListenable`s;
the controller itself is a `Listenable`, so `AnimatedBuilder(animation:
controller, ...)` rebuilds a timeline or a frame counter.

**Play once when selected.** A tab bar or a segmented control plays its icon
through once each time it is picked, and leaves it on its last frame:

```dart
NavigationBar(
  selectedIndex: selected,
  onDestinationSelected: (index) {
    setState(() => selected = index);
    tabControllers[index].playOnce();
  },
  destinations: [
    for (var i = 0; i < bundles.length; i++)
      NavigationDestination(
        icon: LavaIcon(
          bundle: bundles[i],
          controller: tabControllers[i],
          size: 28,
          autoPlay: false,
        ),
        label: labels[i],
      ),
  ],
)
```

`playOnce` runs from the first frame to `loopEndFrame` and stops with
`LavaPlaybackStatus.completed`, whatever the manifest's loop setting; `play()`
goes back to looping playback.

**Intro, then loop.** Bundles whose manifest sets `loopStartFrame` /
`loopEndFrame` play their intro once and then cycle the loop section. The same
can be done by hand with `controller.configure(totalFrames: 48, loopStartFrame:
14, loopEndFrame: 33)` followed by `seekToFrame(0)` and `play()`.

### Make it interactive

```dart
LavaIcon(
  bundle: bundle,
  size: 120,
  interactive: true,   // hover tilt + press bounce (+ light haptics)
  dragToRotate: true,  // horizontal drag scrubs the frames (default)
  scrubOnHover: false, // true: the pointer position picks the frame
  onTap: () {},
  onStateChanged: (state) {}, // idle / hover / pressed
)
```

With `interactive: true` the icon does not auto-play unless `autoPlay: true`
is passed, so a paused model can be turned by hand. Bundles rendered as full
turns (the helmet above: 72 frames, one revolution) become little turntables;
a drag during playback pauses it and playback resumes where the drag ended.

`LavaInteractive` is also usable on its own, around any widget, with
`maxTiltAngle`, `pressedScale`, `perspective`, `enableTilt`, `enableBounce` and
`enableHaptics` to tune the feel.

### Reduced motion

Leave the icon on its first frame when the platform asks for less motion:

```dart
LavaIcon(
  bundle: bundle,
  size: 64,
  autoPlay: !MediaQuery.disableAnimationsOf(context),
)
```

A still first frame is a complete icon: every bundle starts from its rest
pose.

### Demo bundles

`LavaIcon.demo(demoType: LavaDemoType.rocket)` shows one of the demo icons
when the host app ships its bundle under `assets/lava/<name>/` (see
`LavaBundle.demoAssetPaths`; the `_hd` variant is picked up for large icons).
The Macintosh and sunflower demos also have a procedural fallback drawn with
`Canvas`, used when no asset is bundled, which is what the package's tests use.

### Grid atlases

Besides OpenLava bundles, `LavaIcon.asset(imageAsset: ..., manifestAsset:
...)` and `LavaBundle.fromAsset` / `fromMemory` play a plain sprite sheet: a
manifest with `tileWidth`, `tileHeight`, `columns`, `rows`, `totalFrames` and
`frameRate`, and one image laid out left to right, top to bottom.

## Making your own icons

The icons above were made with the Python pipeline in [`tool/`](tool/README.md)
(`python3 -m pip install Pillow numpy`). The short version:

**Canvas.** 180 x 162 pixels at `"density": 2` (90 x 81 logical pixels, the
Airbnb size), rendered at 4x and downsampled. Icons shown at 120 logical pixels
or more get a second bundle at 360 x 324 (`--density 4`, `LAVA_SCALE=2` for the
generators), which `LavaIcon.demo` switches to on its own.

**Composition.** The subject fills about 72 % of the canvas, with its base at
about 80 % of the height, so a contact shadow fits under it and a hover or bob
never clips. Hero parts must be large in the still: a 180-pixel canvas has no
room for detail.

**Motion.** 48 frames at 30 fps (1.6 s). Every motion is a function of the loop
phase - `sin(2πt)`, `cos(2πt)` and whole multiples of them - so the last frame
leads back into the first and the loop is seamless. Give each icon one primary
motion (a yaw rock, a bob, a turn) and one or two secondary ones (a highlight
sweep, a blink, a particle).

**Encode.**

```sh
python3 tool/openlava_encode.py assets/lava/bingo_ball --webp 88 frames/frame_*.png
```

`openlava_encode.py` keys identical tiles across frames (OpenLava's packing
rules), writes the key frame, the atlas and the manifest, then decodes the
bundle like a player and reports the error. `--webp 88` is a good default; aim
for 250 KB or less per bundle. `--avif 70 --fallback-webp 90` writes an AVIF
atlas with a WebP fallback for apps that also target the web. `--density 4`
marks a large-preview bundle. `tool/openlava_gif.py <bundle> out.gif` renders
a bundle to a GIF for documentation.

**Three ways to get frames.**

| Route | Script | When |
| --- | --- | --- |
| Still + motion | `animate_icon.py` | one rendered still and secondary motion (a rock, a bob, a sway, a blink) is enough |
| Lit / unlit pair | `relight_icon.py` | the icon has a light source that must light the rest of it (a flame, fairy lights), or a part with two states |
| Procedural 3D | `sdf_scenes.py` + `lava_sdf.py` | the object must turn on its own axis: a small numpy SDF ray marcher with soft key light, ambient occlusion, satin specular and a contact shadow |

[`tool/README.md`](tool/README.md) is the full reference: prompts for the
stills, keying, premultiplied-alpha transforms, light passes, cloth and
particle simulation, segment-based bundles (a play/pause key) and the packing
rules.

## How it works

1. `LavaManifest` parses an OpenLava or grid manifest: canvas, fps, loop
   bounds, images and per-frame tile lists.
2. `LavaBundle` loads and decodes the images (with AVIF/WebP fallback and
   per-path caching) and owns the `LavaFrameCompositor`.
3. `LavaFrameCompositor` compiles each diff frame into `Float32List`
   transforms and rects, composes it with `Canvas.drawRawAtlas` at native
   resolution and caches the result.
4. `LavaPainter` is a `CustomPainter` that draws the composed frame (or the
   grid tile, through `TileMath`) scaled into the widget with
   `drawImageRect`, driven by a `LavaController` ticker.
5. `LavaInteractive` wraps it in a perspective `Transform` with spring
   physics and maps drags and hovers to frames.

## License

MIT, copyright 2026 [Matheus Dias](https://github.com/Mathvdias).
