import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/src/model/lava_manifest.dart';

void main() {
  group('LavaManifest', () {
    test('parses complete JSON correctly', () {
      final json = {
        'version': 1,
        'frameRate': 60,
        'tileWidth': 128,
        'tileHeight': 128,
        'columns': 6,
        'rows': 4,
        'totalFrames': 24,
        'loop': true,
        'loopStartFrame': 2,
        'loopEndFrame': 22,
      };

      final manifest = LavaManifest.fromJson(json);

      expect(manifest.version, 1);
      expect(manifest.frameRate, 60);
      expect(manifest.tileWidth, 128);
      expect(manifest.tileHeight, 128);
      expect(manifest.columns, 6);
      expect(manifest.rows, 4);
      expect(manifest.totalFrames, 24);
      expect(manifest.loop, isTrue);
      expect(manifest.loopStartFrame, 2);
      expect(manifest.loopEndFrame, 22);
      expect(manifest.frameDuration.inMilliseconds, closeTo(16, 1));
      expect(manifest.totalDuration.inMilliseconds, closeTo(400, 10));
    });

    test('applies safe defaults when optional fields are omitted', () {
      final json = {'tileWidth': 64, 'tileHeight': 64, 'columns': 4, 'rows': 4};

      final manifest = LavaManifest.fromJson(json);

      expect(manifest.version, 1);
      expect(manifest.frameRate, 30);
      expect(manifest.totalFrames, 16);
      expect(manifest.loop, isTrue);
      expect(manifest.loopStartFrame, 0);
      expect(manifest.loopEndFrame, 15);
    });

    test('serializes to JSON and round-trips identically', () {
      const original = LavaManifest(
        tileWidth: 48,
        tileHeight: 48,
        columns: 4,
        rows: 3,
        totalFrames: 12,
        frameRate: 24,
        loop: false,
      );

      final serialized = original.toJson();
      final reconstructed = LavaManifest.fromJson(serialized);

      expect(reconstructed, equals(original));
      expect(reconstructed.hashCode, equals(original.hashCode));
    });

    test('copyWith creates modified copy correctly', () {
      const original = LavaManifest(
        tileWidth: 64,
        tileHeight: 64,
        columns: 4,
        rows: 4,
        totalFrames: 16,
      );

      final modified = original.copyWith(frameRate: 45, loop: false);

      expect(modified.frameRate, 45);
      expect(modified.loop, isFalse);
      expect(modified.tileWidth, original.tileWidth);
    });

    test('parses official OpenLava format manifest correctly', () {
      final openLavaJson = {
        'version': 1,
        'fps': 30,
        'cellSize': 32,
        'diffImageSize': 2048,
        'width': 180,
        'height': 162,
        'density': 2,
        'alpha': true,
        'images': [
          {'url': 'image_1.avif'},
          {'url': 'image_2.avif'},
        ],
        'frames': [
          {'type': 'key', 'imageIndex': 0},
          {
            'type': 'diff',
            'diffs': [
              [0, 0, 6, 1, 0],
              [1, 0, 3, 4, 7],
            ],
          },
        ],
      };

      final manifest = LavaManifest.fromJson(openLavaJson);

      expect(manifest.version, 1);
      expect(manifest.frameRate, 30);
      expect(manifest.cellSize, 32);
      expect(manifest.diffImageSize, 2048);
      expect(manifest.tileWidth, 180);
      expect(manifest.tileHeight, 162);
      expect(manifest.totalFrames, 2);
      expect(manifest.images, ['image_1.avif', 'image_2.avif']);
      expect(manifest.rawFrames.length, 2);
    });

    test('parses and round-trips fallbackUrl entries', () {
      final manifest = LavaManifest.fromJson({
        'width': 180,
        'height': 162,
        'images': [
          {'url': 'image_1.avif', 'fallbackUrl': 'image_1.webp'},
          {'url': 'image_2.png'},
        ],
        'frames': [
          {'type': 'key', 'imageIndex': 0},
        ],
      });

      expect(manifest.images, ['image_1.avif', 'image_2.png']);
      expect(manifest.imageFallbacks, ['image_1.webp', null]);
      expect(manifest.toJson()['images'], [
        {'url': 'image_1.avif', 'fallbackUrl': 'image_1.webp'},
        {'url': 'image_2.png'},
      ]);
    });

    test('copyWith keeps the OpenLava fields it does not override', () {
      final manifest = LavaManifest.fromJson({
        'width': 180,
        'height': 162,
        'cellSize': 32,
        'diffImageSize': 2048,
        'alpha': false,
        'images': [
          {'url': 'image_1.avif', 'fallbackUrl': 'image_1.webp'},
        ],
        'frames': [
          {'type': 'key', 'imageIndex': 0},
        ],
      }).copyWith(frameRate: 24);

      expect(manifest.frameRate, 24);
      expect(manifest.cellSize, 32);
      expect(manifest.diffImageSize, 2048);
      expect(manifest.alpha, isFalse);
      expect(manifest.images, ['image_1.avif']);
      expect(manifest.imageFallbacks, ['image_1.webp']);
      expect(manifest.rawFrames, hasLength(1));
    });
  });
}
