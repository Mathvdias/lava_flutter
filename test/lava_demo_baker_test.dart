import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/lava_flutter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LavaDemoBaker', () {
    test(
      'bakeAtlas generates valid 3D texture atlas and caches result',
      () async {
        LavaDemoBaker.clearCache();

        final atlas = await LavaDemoBaker.bakeAtlas();
        expect(atlas, isNotNull);
        expect(atlas.width, 6 * 128);
        expect(atlas.height, 4 * 128);

        // Verify subsequent call hits cache
        final cachedAtlas = await LavaDemoBaker.bakeAtlas();
        expect(identical(atlas, cachedAtlas), isTrue);

        LavaDemoBaker.clearCache();
      },
    );

    test(
      'bakeTreeAtlas generates valid nature tree 3D texture atlas',
      () async {
        LavaDemoBaker.clearCache();

        final treeAtlas = await LavaDemoBaker.bakeTreeAtlas();
        expect(treeAtlas, isNotNull);
        expect(treeAtlas.width, 6 * 128);
        expect(treeAtlas.height, 4 * 128);

        final cachedTreeAtlas = await LavaDemoBaker.bakeTreeAtlas();
        expect(identical(treeAtlas, cachedTreeAtlas), isTrue);

        LavaDemoBaker.clearCache();
      },
    );

    test('defaultManifest matches baked atlas geometry', () {
      const manifest = LavaDemoBaker.defaultManifest;
      expect(manifest.totalFrames, 24);
      expect(manifest.columns, 6);
      expect(manifest.rows, 4);
      expect(manifest.tileWidth, 128);
      expect(manifest.tileHeight, 128);
      expect(manifest.columns * manifest.tileWidth, 768);
      expect(manifest.rows * manifest.tileHeight, 512);
    });
  });
}
