import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/lava_flutter.dart';

class _MissingAssetBundle extends Fake implements AssetBundle {
  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    throw Exception('Asset not found: $key');
  }

  @override
  Future<ByteData> load(String key) async {
    throw Exception('Asset not found: $key');
  }
}

/// Bytes that carry the AVIF container signature but no decodable payload.
final Uint8List _brokenAvif = Uint8List.fromList([
  0,
  0,
  0,
  28,
  ...'ftypavif'.codeUnits,
  ...List.filled(52, 7),
]);

/// In-memory OpenLava bundle: `image_N.avif` primaries with `image_N.webp`
/// fallbacks. [primary] is what the `.avif` names serve (`null` = 404).
class _FallbackAssetBundle extends Fake implements AssetBundle {
  _FallbackAssetBundle(
    this.fallbackBytes, {
    required this.primary,
    this.canvasWidth = 32,
  });

  final Uint8List fallbackBytes;
  final Uint8List? primary;

  /// Manifest width: above [LavaBundle.demoBaseWidth] it is a large preview.
  final int canvasWidth;
  final List<String> loads = [];

  @override
  Future<String> loadString(String key, {bool cache = true}) async =>
      jsonEncode({
        'version': 1,
        'fps': 30,
        'cellSize': 32,
        'width': canvasWidth,
        'height': 32,
        'images': [
          {'url': 'image_1.avif', 'fallbackUrl': 'image_1.webp'},
          {'url': 'image_2.avif', 'fallbackUrl': 'image_2.webp'},
        ],
        'frames': [
          {'type': 'key', 'imageIndex': 0},
          {
            'type': 'diff',
            'diffs': [
              [1, 0, 1, 1, 0],
            ],
          },
        ],
      });

  @override
  Future<ByteData> load(String key) async {
    loads.add(key.split('/').last);
    if (key.endsWith('.avif')) {
      if (primary == null) throw Exception('404: $key');
      return ByteData.sublistView(primary!);
    }
    return ByteData.sublistView(fallbackBytes);
  }
}

class _NoFallbackAssetBundle extends Fake implements AssetBundle {
  @override
  Future<String> loadString(String key, {bool cache = true}) async =>
      jsonEncode({
        'width': 32,
        'height': 32,
        'images': [
          {'url': 'image_1.avif'},
        ],
        'frames': [
          {'type': 'key', 'imageIndex': 0},
        ],
      });

  @override
  Future<ByteData> load(String key) async =>
      ByteData.sublistView(Uint8List.fromList(List.filled(64, 7)));
}

Future<Uint8List> _pngBytes({int width = 32}) async {
  final recorder = ui.PictureRecorder();
  ui.Canvas(recorder).drawPaint(ui.Paint()..color = const ui.Color(0xFF00FF00));
  final image = await recorder.endRecording().toImage(width, 32);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LavaDemoBaker & LavaBundle', () {
    test('bakes procedural demo atlas and constructs LavaBundle', () async {
      final bundle = await LavaBundle.procedural(forceRegenerate: true);

      expect(bundle.atlas!.width, 768); // 6 cols * 128
      expect(bundle.atlas!.height, 512); // 4 rows * 128
      expect(bundle.manifest.totalFrames, 24);
      expect(bundle.manifest.columns, 6);
      expect(bundle.manifest.rows, 4);
      expect(bundle.manifest.tileWidth, 128);
      expect(bundle.manifest.tileHeight, 128);

      LavaDemoBaker.clearCache();
    });

    test('reuses cached image across subsequent calls unless forced', () async {
      final bundle1 = await LavaBundle.procedural();
      final bundle2 = await LavaBundle.procedural();

      expect(identical(bundle1.atlas, bundle2.atlas), isTrue);

      LavaDemoBaker.clearCache();
    });

    test('demo() falls back to the procedural atlas when the OpenLava asset '
        'directory is not bundled', () async {
      final bundle = await LavaBundle.demo(
        type: LavaDemoType.sunflower,
        bundle: _MissingAssetBundle(),
      );

      expect(bundle.images, isEmpty);
      expect(bundle.atlas, isNotNull);
      expect(bundle.manifest, LavaDemoBaker.defaultManifest);

      LavaDemoBaker.clearCache();
    });

    test('demo() rethrows for campfire when assets are missing', () async {
      expect(
        () => LavaBundle.demo(
          type: LavaDemoType.campfire,
          bundle: _MissingAssetBundle(),
        ),
        throwsA(isA<Object>()),
      );
    });

    test(
      'demo() rethrows for senna and christmasTree when assets are missing',
      () async {
        expect(
          () => LavaBundle.demo(
            type: LavaDemoType.senna,
            bundle: _MissingAssetBundle(),
          ),
          throwsA(isA<Object>()),
        );
        expect(
          () => LavaBundle.demo(
            type: LavaDemoType.christmasTree,
            bundle: _MissingAssetBundle(),
          ),
          throwsA(isA<Object>()),
        );
      },
    );

    /// Runs [body] with the web policy (primary first) and restores the default.
    Future<void> asOnTheWeb(
      WidgetTester tester,
      Future<void> Function() body,
    ) => tester.runAsync(() async {
      final previous = LavaBundle.preferFallbackImages;
      LavaBundle.evictOpenLavaCache();
      LavaBundle.preferFallbackImages = false;
      try {
        await body();
      } finally {
        LavaBundle.preferFallbackImages = previous;
        LavaBundle.evictOpenLavaCache();
      }
    });

    testWidgets(
      'a primary image that decodes is used and no fallback is fetched',
      (tester) async {
        await asOnTheWeb(tester, () async {
          final assets = _FallbackAssetBundle(
            await _pngBytes(),
            primary: await _pngBytes(),
          );

          final bundle = await LavaBundle.openLavaAsset(
            assetPath: 'icons/ok',
            bundle: assets,
          );

          expect(bundle.images, hasLength(2));
          expect(assets.loads, ['image_1.avif', 'image_2.avif']);
          expect(LavaBundle.undecodableExtensions, isEmpty);
        });
      },
    );

    testWidgets('an undecodable AVIF falls back and is remembered', (
      tester,
    ) async {
      await asOnTheWeb(tester, () async {
        final assets = _FallbackAssetBundle(
          await _pngBytes(),
          primary: _brokenAvif,
        );

        final bundle = await LavaBundle.openLavaAsset(
          assetPath: 'icons/a',
          bundle: assets,
        );
        expect(bundle.images, hasLength(2));
        expect(bundle.images.first.width, 32);
        expect(bundle.manifest.imageFallbacks, [
          'image_1.webp',
          'image_2.webp',
        ]);
        // The first failure is remembered: image_2.avif is never requested.
        expect(assets.loads, ['image_1.avif', 'image_1.webp', 'image_2.webp']);
        expect(LavaBundle.undecodableExtensions, {'avif'});

        assets.loads.clear();
        await LavaBundle.openLavaAsset(assetPath: 'icons/b', bundle: assets);
        expect(assets.loads, ['image_1.webp', 'image_2.webp']);
      });
    });

    testWidgets('bytes that are not an AVIF at all do not blame the decoder', (
      tester,
    ) async {
      await asOnTheWeb(tester, () async {
        // An SPA host answers a missing asset with 200 + index.html.
        final html = Uint8List.fromList(
          '<!doctype html><html></html>'.codeUnits,
        );
        final assets = _FallbackAssetBundle(await _pngBytes(), primary: html);

        final bundle = await LavaBundle.openLavaAsset(
          assetPath: 'icons/html',
          bundle: assets,
        );

        expect(bundle.images, hasLength(2));
        expect(LavaBundle.undecodableExtensions, isEmpty);
        expect(assets.loads, [
          'image_1.avif',
          'image_1.webp',
          'image_2.avif',
          'image_2.webp',
        ]);
      });
    });

    testWidgets(
      'a primary decoded with the wrong width is replaced by the fallback',
      (tester) async {
        await asOnTheWeb(tester, () async {
          final assets = _FallbackAssetBundle(
            await _pngBytes(),
            primary: await _pngBytes(width: 64), // manifest says 32
          );

          final bundle = await LavaBundle.openLavaAsset(
            assetPath: 'icons/wide',
            bundle: assets,
          );

          expect(bundle.images.first.width, 32);
          expect(assets.loads.take(2), ['image_1.avif', 'image_1.webp']);
          expect(LavaBundle.undecodableExtensions, isEmpty);
        });
      },
    );

    testWidgets(
      'a primary image that fails to load does not blame the decoder',
      (tester) async {
        await asOnTheWeb(tester, () async {
          final assets = _FallbackAssetBundle(await _pngBytes(), primary: null);

          final bundle = await LavaBundle.openLavaAsset(
            assetPath: 'icons/m',
            bundle: assets,
          );

          expect(bundle.images, hasLength(2));
          expect(LavaBundle.undecodableExtensions, isEmpty);
        });
      },
    );

    testWidgets(
      'native platforms load the fallback without touching the AVIF',
      (tester) async {
        await tester.runAsync(() async {
          LavaBundle.evictOpenLavaCache();
          expect(LavaBundle.preferFallbackImages, isTrue);
          final assets = _FallbackAssetBundle(
            await _pngBytes(),
            primary: _brokenAvif,
          );

          await LavaBundle.openLavaAsset(assetPath: 'icons/n', bundle: assets);

          expect(assets.loads, ['image_1.webp', 'image_2.webp']);
          expect(LavaBundle.undecodableExtensions, isEmpty);
          LavaBundle.evictOpenLavaCache();
        });
      },
    );

    testWidgets('releasing a large-preview bundle evicts and disposes it', (
      tester,
    ) async {
      await tester.runAsync(() async {
        LavaBundle.evictOpenLavaCache();
        final wide = await _pngBytes(width: 360);
        final assets = _FallbackAssetBundle(
          wide,
          primary: null,
          canvasWidth: 360,
        );

        final bundle = await LavaBundle.openLavaAsset(
          assetPath: 'icons/hd',
          bundle: assets,
        );
        bundle
          ..retain()
          ..retain()
          ..release();
        await Future<void>.delayed(Duration.zero);
        expect(bundle.isDisposed, isFalse, reason: 'one user is still there');

        bundle.release();
        await Future<void>.delayed(Duration.zero);
        expect(bundle.isDisposed, isTrue);

        // Evicted: asking again decodes a fresh bundle instead of the dead one.
        final again = await LavaBundle.openLavaAsset(
          assetPath: 'icons/hd',
          bundle: assets,
        );
        expect(again, isNot(same(bundle)));
        expect(again.isDisposed, isFalse);
        LavaBundle.evictOpenLavaCache();
      });
    });

    testWidgets('releasing a standard bundle keeps it cached', (tester) async {
      await tester.runAsync(() async {
        LavaBundle.evictOpenLavaCache();
        final assets = _FallbackAssetBundle(await _pngBytes(), primary: null);

        final bundle = await LavaBundle.openLavaAsset(
          assetPath: 'icons/std',
          bundle: assets,
        );
        bundle
          ..retain()
          ..release();
        await Future<void>.delayed(Duration.zero);

        expect(bundle.isDisposed, isFalse);
        expect(
          await LavaBundle.openLavaAsset(
            assetPath: 'icons/std',
            bundle: assets,
          ),
          same(bundle),
        );
        LavaBundle.evictOpenLavaCache();
      });
    });

    testWidgets('a bundle retained again within the same frame survives', (
      tester,
    ) async {
      await tester.runAsync(() async {
        LavaBundle.evictOpenLavaCache();
        final wide = await _pngBytes(width: 360);
        final assets = _FallbackAssetBundle(
          wide,
          primary: null,
          canvasWidth: 360,
        );
        final bundle = await LavaBundle.openLavaAsset(
          assetPath: 'icons/swap',
          bundle: assets,
        );

        bundle
          ..retain()
          ..release()
          ..retain(); // handed to another widget before the microtask runs
        await Future<void>.delayed(Duration.zero);

        expect(bundle.isDisposed, isFalse);
        LavaBundle.evictOpenLavaCache();
      });
    });

    testWidgets('openLavaAsset rethrows when there is no fallback to try', (
      tester,
    ) async {
      await tester.runAsync(() async {
        LavaBundle.evictOpenLavaCache();
        final assets = _NoFallbackAssetBundle();
        await expectLater(
          LavaBundle.openLavaAsset(assetPath: 'icons/c', bundle: assets),
          throwsA(isA<Exception>()),
        );
        LavaBundle.evictOpenLavaCache();
      });
    });
  });
}
