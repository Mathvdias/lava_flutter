import 'dart:async';
import 'dart:convert';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../demo/lava_demo_baker.dart';
import '../engine/lava_frame_compositor.dart';
import '../model/lava_manifest.dart';
import '../model/lava_types.dart';
import 'browser_image_decoder_stub.dart'
    if (dart.library.js_interop) 'browser_image_decoder_web.dart';

/// Container encapsulating a decoded texture atlas [ui.Image] and its
/// associated [LavaManifest] layout parameters.
class LavaBundle {
  LavaBundle({
    this.atlas,
    this.images = const [],
    required this.manifest,
    this.imageFiles = const [],
  });

  /// Hardware texture holding animation frames for single-atlas grid mode.
  final ui.Image? atlas;

  /// Multi-image hardware textures for OpenLava diff mode.
  final List<ui.Image> images;

  /// Structural layout and timing metadata.
  final LavaManifest manifest;

  /// File actually decoded for each entry of [images] (`image_2.avif`, or
  /// `image_2.webp` when the fallback was used). Empty for in-memory bundles.
  final List<String> imageFiles;

  LavaFrameCompositor? _compositor;

  int _retainCount = 0;
  bool _disposed = false;
  String? _cacheKey;

  /// Whether [dispose] has run: the textures are gone and the bundle must be
  /// loaded again.
  bool get isDisposed => _disposed;

  /// A widget that puts this bundle on screen calls [retain], and [release]
  /// when it lets go. When the last user leaves, the composed frames are
  /// dropped, and a large-preview bundle (its atlas is 2-22 MB of texture) is
  /// evicted from the loader cache and disposed; the small standard bundles
  /// stay cached, which is what makes switching icons instant.
  void retain() => _retainCount++;

  /// See [retain].
  void release() {
    if (_retainCount > 0) _retainCount--;
    if (_retainCount > 0) return;
    // Not synchronously: a rebuild may hand the same bundle to another widget
    // within this frame.
    scheduleMicrotask(() {
      if (_retainCount > 0 || _disposed) return;
      _compositor?.clearCache();
      final key = _cacheKey;
      if (key != null && manifest.tileWidth > demoBaseWidth) {
        _openLavaCache.remove(key);
        dispose();
      }
    });
  }

  /// Frame assembler for OpenLava key/diff bundles (`null` for grid atlases).
  ///
  /// It lives with the bundle so every widget showing it shares one cache of
  /// composed frames.
  LavaFrameCompositor? get compositor {
    if (manifest.rawFrames.isEmpty || images.isEmpty) return null;
    return _compositor ??= LavaFrameCompositor(
      images: images,
      manifest: manifest,
    );
  }

  /// Asset directory (inside the host application) holding the OpenLava bundle
  /// for each built-in [LavaDemoType].
  static const Map<LavaDemoType, String> demoAssetPaths = {
    LavaDemoType.macintosh: 'assets/lava/macintosh',
    LavaDemoType.sunflower: 'assets/lava/sunflower',
    LavaDemoType.lavaLamp: 'assets/lava/lavalamp',
    LavaDemoType.campfire: 'assets/lava/campfire',
    LavaDemoType.rocket: 'assets/lava/rocket',
    LavaDemoType.senna: 'assets/lava/senna',
    LavaDemoType.christmasTree: 'assets/lava/christmastree',
    LavaDemoType.f1Car: 'assets/lava/f1car',
    LavaDemoType.f1Front: 'assets/lava/f1front',
    LavaDemoType.sennaMp4: 'assets/lava/sennamp4',
  };

  /// Canvas width of the standard demo bundles (the Airbnb size, density 2).
  static const int demoBaseWidth = 180;

  /// Large-preview variant of [demoAssetPaths]: the same animation rendered at
  /// 360x324 (`"density": 4`), for icons painted well above [demoBaseWidth]
  /// device pixels. Only fetched when asked for with `hd: true`.
  static Map<LavaDemoType, String> get demoHdAssetPaths => {
    for (final entry in demoAssetPaths.entries) entry.key: '${entry.value}_hd',
  };

  /// Loads the built-in demo bundle for [type].
  ///
  /// Every demo is an OpenLava diff tileset (`manifest.json` + `image_1.png`
  /// key frame + `image_2.png` diff atlas) declared by the host application
  /// under [demoAssetPaths]. When the asset directory is not bundled (for
  /// example inside the package's own tests) the Macintosh and sunflower icons fall
  /// back to the procedural [LavaDemoBaker] atlas via [procedural].
  static Future<LavaBundle> demo({
    LavaDemoType type = LavaDemoType.macintosh,
    bool forceRegenerate = false,
    bool hd = false,
    AssetBundle? bundle,
  }) async {
    if (hd) {
      try {
        return await openLavaAsset(
          assetPath: demoHdAssetPaths[type]!,
          bundle: bundle,
        );
      } catch (_) {
        // Hosts that only ship the standard bundles still get an icon.
      }
    }
    try {
      return await openLavaAsset(
        assetPath: demoAssetPaths[type]!,
        bundle: bundle,
      );
    } catch (_) {
      switch (type) {
        case LavaDemoType.macintosh:
        case LavaDemoType.sunflower:
          return procedural(type: type, forceRegenerate: forceRegenerate);
        case LavaDemoType.lavaLamp:
        case LavaDemoType.campfire:
        case LavaDemoType.rocket:
        case LavaDemoType.senna:
        case LavaDemoType.christmasTree:
        case LavaDemoType.f1Car:
        case LavaDemoType.f1Front:
        case LavaDemoType.sennaMp4:
          rethrow;
      }
    }
  }

  /// Bakes the procedural Canvas-rendered demo atlas for [type]
  /// (only [LavaDemoType.macintosh] and [LavaDemoType.sunflower] are supported;
  /// the sunflower falls back to the procedural nature tree).
  static Future<LavaBundle> procedural({
    LavaDemoType type = LavaDemoType.macintosh,
    bool forceRegenerate = false,
  }) async {
    assert(
      type == LavaDemoType.macintosh || type == LavaDemoType.sunflower,
      'Only the Macintosh and sunflower demos have a procedural renderer.',
    );
    final image = await LavaDemoBaker.bakeAtlas(
      type: type,
      forceRegenerate: forceRegenerate,
    );
    return LavaBundle(atlas: image, manifest: LavaDemoBaker.defaultManifest);
  }

  /// Convenience shortcut to load the sunflower demo bundle.
  static Future<LavaBundle> demoSunflower({bool forceRegenerate = false}) =>
      demo(type: LavaDemoType.sunflower, forceRegenerate: forceRegenerate);

  static final Map<String, Future<LavaBundle>> _openLavaCache = {};

  /// Loads an OpenLava format animation directory containing `manifest.json` and image tilesets.
  ///
  /// Decoded bundles are shared: every icon pointing at the same [assetPath]
  /// reuses one set of textures, so they must not be disposed individually
  /// (use [evictOpenLavaCache] to release them).
  static Future<LavaBundle> openLavaAsset({
    required String assetPath,
    AssetBundle? bundle,
  }) {
    final effectiveBundle = bundle ?? rootBundle;
    final cacheKey = '${identityHashCode(effectiveBundle)}:$assetPath';
    return _openLavaCache[cacheKey] ??= _decodeOpenLava(
      assetPath,
      effectiveBundle,
    ).then((loaded) => loaded.._cacheKey = cacheKey).onError((
      Object error,
      StackTrace stackTrace,
    ) {
      _openLavaCache.remove(cacheKey);
      Error.throwWithStackTrace(error, stackTrace);
    });
  }

  /// Empties the [openLavaAsset] cache and disposes its bundles (loads still
  /// in flight are disposed as soon as they finish).
  static void evictOpenLavaCache() {
    final pending = _openLavaCache.values.toList();
    _openLavaCache.clear();
    _undecodableExtensions.clear();
    for (final future in pending) {
      future.then((bundle) => bundle.dispose(), onError: (Object _) {});
    }
  }

  // File extensions this process already failed to decode (an AVIF atlas on a
  // system without an AV1 decoder): later bundles go straight to the fallback
  // instead of fetching and rejecting the primary file again.
  static final Set<String> _undecodableExtensions = {};

  /// File extensions that failed to decode in this process and are now served
  /// from their `fallbackUrl` (diagnostics: `{'avif'}` means no AV1 decoder).
  static Set<String> get undecodableExtensions =>
      Set.unmodifiable(_undecodableExtensions);

  /// Whether a manifest's `fallbackUrl` is loaded *instead of* its `url`.
  ///
  /// Defaults to `true` off the web. The primary image of a bundle is usually
  /// AVIF, and native decoders cannot be trusted with it behind a try/catch:
  /// Android 12 to 15 decode AVIF but silently drop the alpha channel (the
  /// atlas comes back opaque, no exception), Linux and older Android have no
  /// AV1 decoder at all, and assets are embedded in native apps anyway, so
  /// nothing is saved by preferring the smaller file. On the web only the file
  /// that is actually requested gets downloaded, and the browser decodes AVIF.
  static bool preferFallbackImages = !kIsWeb;

  static String _extensionOf(String name) =>
      name.contains('.')
          ? name.substring(name.lastIndexOf('.') + 1).toLowerCase()
          : '';

  /// Decodes `name`, or its `fallback`, and reports which file it was.
  static Future<(ui.Image, String)> _decodeWithFallback(
    AssetBundle bundle,
    String assetPath,
    String name,
    String? fallback, {
    int? expectedWidth,
  }) async {
    Future<(ui.Image, String)> decode(String file) async => (
      await _decodeImage(
        await _loadBytes(bundle, '$assetPath/$file'),
        mimeType: _mimeTypes[_extensionOf(file)],
      ),
      file,
    );

    if (fallback == null) return decode(name);

    final extension = _extensionOf(name);
    if (preferFallbackImages || _undecodableExtensions.contains(extension)) {
      try {
        return await decode(fallback);
      } catch (_) {
        // A bundle shipped without its fallback file still has its primary.
        return decode(name);
      }
    }

    final Uint8List bytes;
    try {
      bytes = await _loadBytes(bundle, '$assetPath/$name');
    } catch (_) {
      // A missing file or a network error says nothing about the decoder.
      return decode(fallback);
    }

    ui.Image? image;
    try {
      image = await _decodeImage(bytes, mimeType: _mimeTypes[extension]);
    } catch (_) {
      // Only blame the decoder for bytes that really are that format: a host
      // with an SPA rewrite answers a missing asset with 200 + index.html, and
      // one broken file must not switch every other bundle to its fallback.
      if (_sniffExtension(bytes) == extension) {
        _undecodableExtensions.add(extension);
      }
    }
    // Some platform decoders hand back a bogus image instead of failing.
    if (image != null &&
        expectedWidth != null &&
        image.width != expectedWidth) {
      image.dispose();
      image = null;
    }
    return image == null ? decode(fallback) : (image, name);
  }

  /// Container signature -> extension (`null` when the bytes are none of the
  /// formats bundles use).
  static String? _sniffExtension(Uint8List bytes) {
    bool at(int offset, String ascii) {
      if (bytes.length < offset + ascii.length) return false;
      for (var i = 0; i < ascii.length; i++) {
        if (bytes[offset + i] != ascii.codeUnitAt(i)) return false;
      }
      return true;
    }

    if (at(4, 'ftypavif') || at(4, 'ftypavis')) return 'avif';
    if (at(0, 'RIFF') && at(8, 'WEBP')) return 'webp';
    if (at(1, 'PNG')) return 'png';
    if (bytes.length > 2 && bytes[0] == 0xFF && bytes[1] == 0xD8) return 'jpg';
    return null;
  }

  static Future<Uint8List> _loadBytes(AssetBundle bundle, String key) async {
    final byteData = await bundle.load(key);
    return byteData.buffer.asUint8List(
      byteData.offsetInBytes,
      byteData.lengthInBytes,
    );
  }

  static const Map<String, String> _mimeTypes = {
    'avif': 'image/avif',
    'webp': 'image/webp',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
  };

  static Future<ui.Image> _decodeImage(
    Uint8List bytes, {
    String? mimeType,
  }) async {
    try {
      final codec = await ui.instantiateImageCodec(bytes);
      try {
        return (await codec.getNextFrame()).image;
      } finally {
        codec.dispose();
      }
    } catch (_) {
      // On the web the engine's decoder refuses files the browser itself
      // decodes fine (every still AVIF on Chrome, flutter/flutter#160600):
      // ask the browser directly. If it cannot either, the engine's error is
      // the one worth reporting.
      final type = mimeType ?? _mimeTypes[_sniffExtension(bytes)];
      ui.Image? image;
      try {
        image = type == null ? null : await decodeImageInBrowser(bytes, type);
      } catch (_) {
        image = null;
      }
      if (image == null) rethrow;
      return image;
    }
  }

  static Future<LavaBundle> _decodeOpenLava(
    String assetPath,
    AssetBundle effectiveBundle,
  ) async {
    final jsonStr = await effectiveBundle.loadString(
      '$assetPath/manifest.json',
    );
    final manifestJson = jsonDecode(jsonStr) as Map<String, dynamic>;
    final manifest = LavaManifest.fromJson(manifestJson);

    final keyImages = <int>{
      for (final frame in manifest.rawFrames)
        if (frame is Map && frame['type'] == 'key')
          (frame['imageIndex'] as num?)?.toInt() ?? 0,
    };

    final loadedImages = <ui.Image>[];
    final loadedFiles = <String>[];
    for (var i = 0; i < manifest.images.length; i++) {
      final fallback =
          i < manifest.imageFallbacks.length
              ? manifest.imageFallbacks[i]
              : null;
      try {
        final (image, file) = await _decodeWithFallback(
          effectiveBundle,
          assetPath,
          manifest.images[i],
          fallback,
          // A key image is the canvas itself; any other image is a diff atlas.
          expectedWidth:
              keyImages.contains(i)
                  ? manifest.tileWidth
                  : manifest.diffImageSize,
        );
        loadedImages.add(image);
        loadedFiles.add(file);
      } catch (_) {
        for (final image in loadedImages) {
          image.dispose();
        }
        rethrow;
      }
    }

    return LavaBundle(
      images: loadedImages,
      atlas: loadedImages.isNotEmpty ? loadedImages.first : null,
      manifest: manifest,
      imageFiles: loadedFiles,
    );
  }

  /// Loads a [LavaBundle] from application asset files.
  static Future<LavaBundle> fromAsset({
    required String imageAsset,
    required String manifestAsset,
    AssetBundle? bundle,
  }) async {
    final effectiveBundle = bundle ?? rootBundle;

    final jsonStr = await effectiveBundle.loadString(manifestAsset);
    final manifestJson = jsonDecode(jsonStr) as Map<String, dynamic>;
    final manifest = LavaManifest.fromJson(manifestJson);

    final image = await _decodeImage(
      await _loadBytes(effectiveBundle, imageAsset),
      mimeType: _mimeTypes[_extensionOf(imageAsset)],
    );
    return LavaBundle(atlas: image, manifest: manifest);
  }

  /// Creates a [LavaBundle] from raw in-memory encoded image bytes.
  static Future<LavaBundle> fromMemory({
    required Uint8List imageBytes,
    required LavaManifest manifest,
  }) async {
    return LavaBundle(
      atlas: await _decodeImage(imageBytes),
      manifest: manifest,
    );
  }

  /// Releases the GPU texture resources.
  void dispose() {
    _disposed = true;
    _compositor?.dispose();
    _compositor = null;
    atlas?.dispose();
    for (final img in images) {
      if (img != atlas) {
        img.dispose();
      }
    }
  }
}
