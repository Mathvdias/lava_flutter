# lava_flutter

High-performance, tile-based 3D micro-animation engine for Flutter with native alpha-channel transparency and interactive tactile physics.

Inspired by modern dimensional UI design architectures (such as Airbnb's Lava format), `lava_flutter` brings 3D micro-interactions to Flutter applications with realistic lighting, shadows, and smooth 60/120 FPS playback—without the memory overhead of video decoders.

---

## Features

- **Tile-Based Frame Blitting**: Renders animation frames from a compact tile atlas with zero runtime heap allocations during paint.
- **True Alpha Channel**: Full 32-bit RGBA transparency blending seamlessly into any background.
- **Interactive 3D Tilt**: Real-time perspective matrix transform tracking pointer hover or touch.
- **Elastic Spring Physics**: Natural bounce and compression response on press and release.
- **Playback Control**: Programmatic play, pause, stop, loop boundaries, frame scrubbing, and variable playback speed.
- **Zero Heavy Dependencies**: Pure Flutter rendering via `Canvas.drawImageRect` and Skia/Impeller hardware acceleration.

---

## Getting Started

Add `lava_flutter` to your `pubspec.yaml`:

```yaml
dependencies:
  lava_flutter: ^0.1.0
```

---

## Usage

### 1. Instant 3D Demo Icon

Use one of the built-in demo bundles (`LavaDemoType.macintosh`, `LavaDemoType.sunflower`,
`LavaDemoType.lavaLamp`, `LavaDemoType.campfire`, `LavaDemoType.rocket`,
`LavaDemoType.senna`, `LavaDemoType.christmasTree`). They are OpenLava diff
tilesets that the host app ships under `assets/lava/<name>/` (see `LavaBundle.demoAssetPaths`);
the Macintosh and sunflower fall back to a procedural Canvas atlas when the directory is missing:

```dart
import 'package:flutter/material.dart';
import 'package:lava_flutter/lava_flutter.dart';

class MyScreen extends StatelessWidget {
  const MyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: LavaIcon.demo(
          size: 80,
          interactive: true,
        ),
      ),
    );
  }
}
```

### 2. Loading a Custom Lava Bundle

OpenLava directories (`manifest.json` + `image_1.png` key frame + `image_2.png` diff atlas):

```dart
final bundle = await LavaBundle.openLavaAsset(assetPath: 'assets/lava/sunflower');
```

Single grid atlases:

```dart
final bundle = await LavaBundle.fromAsset(
  manifestAsset: 'assets/icons/cube/manifest.json',
  imageAsset: 'assets/icons/cube/atlas.png',
);

LavaIcon(
  bundle: bundle,
  size: 64,
  interactive: true,
)
```

### 3. Programmatic Playback Control

```dart
final controller = LavaController(
  fps: 30,
  totalFrames: 24,
  autoPlay: true,
  loop: true,
);

// Control playback
controller.pause();
controller.seekToFrame(12);
controller.setSpeed(1.5);
controller.play();

// In widget tree
LavaIcon.demo(
  controller: controller,
  size: 64,
)
```

---

## Producing OpenLava assets

`tool/README.md` documents the pipeline used for the bundled demos: render a still 3D icon on
white, key it and animate it with `tool/animate_icon.py`, then pack the frames into a
key-frame + deduplicated diff atlas with `tool/openlava_encode.py`.

## Architecture Overview

1. **`LavaManifest`**: Parses frame rates, grid dimensions, tile boundaries, and animation loop ranges.
2. **`TileMath`**: Pure coordinate mapping functions calculating source rects in $O(1)$ time with no allocations.
3. **`LavaPainter`**: High-speed `CustomPainter` blitting atlas frames with sub-pixel interpolation.
4. **`LavaInteractive`**: Perspective projection (`Matrix4`) and spring bounce integration.

---

## License

MIT © [Matheus Dias](https://github.com/Mathvdias)
