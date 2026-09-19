import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/src/engine/tile_math.dart';

void main() {
  group('TileMath', () {
    test('getSourceRect calculates correct coordinates for 4-column grid', () {
      // Grid: 4 columns, 64x64 tiles
      // Frame 0: (0, 0)
      final r0 = TileMath.getSourceRect(
        frameIndex: 0,
        tileWidth: 64,
        tileHeight: 64,
        columns: 4,
      );
      expect(r0, const Rect.fromLTWH(0, 0, 64, 64));

      // Frame 1: col 1, row 0 -> (64, 0)
      final r1 = TileMath.getSourceRect(
        frameIndex: 1,
        tileWidth: 64,
        tileHeight: 64,
        columns: 4,
      );
      expect(r1, const Rect.fromLTWH(64, 0, 64, 64));

      // Frame 4: col 0, row 1 -> (0, 64)
      final r4 = TileMath.getSourceRect(
        frameIndex: 4,
        tileWidth: 64,
        tileHeight: 64,
        columns: 4,
      );
      expect(r4, const Rect.fromLTWH(0, 64, 64, 64));

      // Frame 7: col 3, row 1 -> (192, 64)
      final r7 = TileMath.getSourceRect(
        frameIndex: 7,
        tileWidth: 64,
        tileHeight: 64,
        columns: 4,
      );
      expect(r7, const Rect.fromLTWH(192, 64, 64, 64));
    });

    test('getSourceRect handles invalid parameters safely', () {
      final rZeroCols = TileMath.getSourceRect(
        frameIndex: 0,
        tileWidth: 64,
        tileHeight: 64,
        columns: 0,
      );
      expect(rZeroCols, Rect.zero);

      final rNegFrame = TileMath.getSourceRect(
        frameIndex: -5,
        tileWidth: 64,
        tileHeight: 64,
        columns: 4,
      );
      expect(rNegFrame, const Rect.fromLTWH(0, 0, 64, 64));
    });

    test('getDestinationRect centers correctly inside container', () {
      const containerSize = Size(200, 100);
      final dst = TileMath.getDestinationRect(
        containerSize: containerSize,
        tileWidth: 64,
        tileHeight: 64,
        fit: BoxFit.contain,
      );

      // Sized to 100x100 and horizontally centered in 200px width: dx = 50
      expect(dst.width, 100);
      expect(dst.height, 100);
      expect(dst.left, 50);
      expect(dst.top, 0);
    });

    test('frameAtProgress and progressAtFrame calculate symmetrically', () {
      const total = 10;

      expect(TileMath.frameAtProgress(progress: 0.0, totalFrames: total), 0);
      expect(TileMath.frameAtProgress(progress: 0.5, totalFrames: total), 5);
      expect(TileMath.frameAtProgress(progress: 0.99, totalFrames: total), 9);
      expect(
        TileMath.frameAtProgress(progress: 1.0, totalFrames: total),
        0,
      ); // loop wrapped

      expect(TileMath.progressAtFrame(frameIndex: 0, totalFrames: total), 0.0);
      expect(TileMath.progressAtFrame(frameIndex: 9, totalFrames: total), 1.0);
    });
  });
}
