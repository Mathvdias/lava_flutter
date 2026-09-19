import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/lava_flutter.dart';

Future<ui.Image> _solid(int width, int height, List<int> rgba) async {
  final pixels = Uint8List(width * height * 4);
  for (var i = 0; i < pixels.length; i += 4) {
    pixels.setRange(i, i + 4, rgba);
  }
  final buffer = await ui.ImmutableBuffer.fromUint8List(pixels);
  final descriptor = ui.ImageDescriptor.raw(
    buffer,
    width: width,
    height: height,
    pixelFormat: ui.PixelFormat.rgba8888,
  );
  final codec = await descriptor.instantiateCodec();
  final frame = await codec.getNextFrame();
  codec.dispose();
  descriptor.dispose();
  buffer.dispose();
  return frame.image;
}

Future<List<int>> _pixel(ui.Image image, int x, int y) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  final offset = (y * image.width + x) * 4;
  return data!.buffer.asUint8List(offset, 4).toList();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LavaFrameCompositor', () {
    late ui.Image key;
    late ui.Image atlas;
    late LavaFrameCompositor compositor;

    const red = [255, 0, 0, 255];
    const green = [0, 255, 0, 255];

    setUp(() async {
      // 3x2 tiles of 32px, the last column / row overhang the 80x48 frame.
      key = await _solid(80, 48, red);
      atlas = await _solid(64, 32, green);
      compositor = LavaFrameCompositor(
        images: [key, atlas],
        manifest: const LavaManifest(
          tileWidth: 80,
          tileHeight: 48,
          columns: 1,
          rows: 3,
          totalFrames: 3,
          cellSize: 32,
          rawFrames: [
            {'type': 'key', 'imageIndex': 0},
            {
              'type': 'diff',
              'diffs': [
                [0, 0, 3, 2, 0],
                [1, 1, 1, 1, 5],
              ],
            },
            {
              'type': 'diff',
              'diffs': [
                [1, 0, 1, 1, 0],
              ],
            },
          ],
        ),
      );
    });

    tearDown(() {
      compositor.dispose();
      key.dispose();
      atlas.dispose();
    });

    test('key frames reuse the source image', () {
      expect(compositor.frame(0), same(key));
      expect(compositor.frame(3), same(key));
    });

    test('diff frames patch the key image pixel-exactly', () async {
      final frame = compositor.frame(1)!;
      expect(frame.width, 80);
      expect(frame.height, 48);
      expect(await _pixel(frame, 0, 0), red);
      expect(await _pixel(frame, 63, 31), red);
      // Tile 5 = column 2, row 1: clamped to the 16x16 px left in the frame.
      expect(await _pixel(frame, 64, 32), green);
      expect(await _pixel(frame, 79, 47), green);
    });

    test('areas no diff covers stay transparent', () async {
      final frame = compositor.frame(2)!;
      expect(await _pixel(frame, 10, 10), green);
      expect(await _pixel(frame, 40, 10), [0, 0, 0, 0]);
    });

    test('keeps composed frames until the byte budget is exceeded', () {
      final first = compositor.frame(1);
      final second = compositor.frame(2);
      expect(compositor.frame(1), same(first));
      expect(compositor.frame(2), same(second));
      expect(compositor.cachedFrameCount, 2);

      // Budget for a single 80x48 RGBA frame: the least recent one goes.
      final tight = LavaFrameCompositor(
        images: [key, atlas],
        manifest: compositor.manifest,
        maxCacheBytes: 80 * 48 * 4,
      );
      final evicted = tight.frame(1);
      tight.frame(2);
      expect(tight.cachedFrameCount, 1);
      expect(tight.frame(1), isNot(same(evicted)));
      tight.dispose();
    });

    test('later blocks replace earlier ones where they overlap', () async {
      final overlap = LavaFrameCompositor(
        images: [key, atlas],
        manifest: const LavaManifest(
          tileWidth: 80,
          tileHeight: 48,
          columns: 1,
          rows: 1,
          totalFrames: 1,
          cellSize: 32,
          rawFrames: [
            {
              'type': 'diff',
              'diffs': [
                [0, 0, 3, 2, 0],
                [1, 0, 1, 1, 1],
                [0, 0, 1, 1, 2],
              ],
            },
          ],
        ),
      );
      final frame = overlap.frame(0)!;
      expect(await _pixel(frame, 16, 16), red);
      expect(await _pixel(frame, 48, 16), green);
      expect(await _pixel(frame, 70, 16), red);
      overlap.dispose();
    });

    test('blits describe where every block of a frame comes from', () {
      final keyFrame = compositor.blits(0);
      expect(keyFrame, hasLength(1));
      expect(keyFrame.single.imageIndex, 0);
      expect(keyFrame.single.destination, const ui.Rect.fromLTWH(0, 0, 80, 48));

      final diff = compositor.blits(1);
      expect(diff.map((b) => b.imageIndex), [0, 1]);
      // Tile 1 of the atlas lands on tile 5 of the frame, clamped to its edge.
      expect(diff.last.source, const ui.Rect.fromLTWH(32, 0, 16, 16));
      expect(diff.last.destination, const ui.Rect.fromLTWH(64, 32, 16, 16));
      expect(compositor.frameCount, 3);
    });

    test(
      'a loop that does not fit the budget keeps only the frame on screen',
      () {
        // Two diff frames of 80x48: a budget for one and a half of them is a
        // partial cache, which would miss on every frame of a loop.
        final partial = LavaFrameCompositor(
          images: [key, atlas],
          manifest: compositor.manifest,
          maxCacheBytes: 80 * 48 * 4 * 3 ~/ 2,
        );
        partial.frame(1);
        partial.frame(2);
        expect(partial.cachedFrameCount, 1);
        expect(partial.cachedBytes, 80 * 48 * 4);

        partial.clearCache();
        expect(partial.cachedFrameCount, 0);
        partial.dispose();
      },
    );

    test('a loop that fits is cached whole and stops compositing', () {
      final first = compositor.frame(1);
      final second = compositor.frame(2);
      for (var lap = 0; lap < 3; lap++) {
        expect(compositor.frame(1), same(first));
        expect(compositor.frame(2), same(second));
      }
      expect(compositor.cachedFrameCount, 2);
    });
  });
}
