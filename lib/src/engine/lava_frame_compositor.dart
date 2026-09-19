import 'dart:collection';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import '../model/lava_manifest.dart';

/// Assembles OpenLava frames at their native resolution.
///
/// A diff frame is a list of tile blocks copied from the key image and the
/// diff atlas onto an empty canvas. Blitting those blocks straight onto a
/// scaled canvas samples across tile borders in the atlas (neighbouring tiles
/// belong to unrelated frames) and leaves seams between adjacent blocks, so
/// the frame is composed 1:1 with nearest sampling first and the finished
/// image is what gets scaled and filtered by [LavaPainter].
///
/// The manifest is compiled once into typed-data blit plans (one
/// [ui.Canvas.drawRawAtlas] call per source image, no per-frame parsing or
/// allocation). Composed frames are cached all-or-nothing: when the whole loop
/// fits in [maxCacheBytes] every frame is kept and a looping icon stops
/// compositing after its first pass; when it does not fit, nothing but the
/// frame on screen is kept. A partial cache is the worst of both: playback
/// walks the frames in order, so an LRU smaller than the loop evicts exactly
/// the frame needed next - a 100 % miss rate that still pins its whole budget.
class LavaFrameCompositor {
  LavaFrameCompositor({
    required this.images,
    required this.manifest,
    this.maxCacheBytes = 40 * 1024 * 1024,
  }) : _plans = _compile(images, manifest);

  /// Decoded images referenced by the manifest (`images[0]` is the key frame).
  final List<ui.Image> images;

  /// OpenLava manifest describing the frames.
  final LavaManifest manifest;

  /// Upper bound for the composed-frame cache (RGBA bytes).
  final int maxCacheBytes;

  final List<_FramePlan?> _plans;

  // Insertion order doubles as recency: hits are re-inserted at the end.
  final LinkedHashMap<int, ui.Image> _cache = LinkedHashMap<int, ui.Image>();

  final ui.Paint _blitPaint =
      ui.Paint()
        ..filterQuality = ui.FilterQuality.none
        ..isAntiAlias = false
        // Later blocks replace whatever an earlier block left underneath.
        ..blendMode = ui.BlendMode.src;

  /// The whole loop, or only the frame on screen (see the class comment).
  late final int _maxCachedFrames = () {
    final frameBytes = manifest.tileWidth * manifest.tileHeight * 4;
    final diffFrames =
        _plans.where((p) => p != null && p.keyImageIndex < 0).length;
    return diffFrames * frameBytes <= maxCacheBytes
        ? math.max(1, diffFrames)
        : 1;
  }();

  /// Number of composed frames currently held.
  int get cachedFrameCount => _cache.length;

  /// Number of frames in the animation.
  int get frameCount => _plans.length;

  /// The copies that build [frameIndex], in paint order: which image each block
  /// of tiles comes from, where it sits there and where it lands in the frame.
  /// A key frame is a single blit of the whole image. Meant for inspectors and
  /// debug overlays; playback never allocates these.
  List<LavaTileBlit> blits(int frameIndex) {
    if (_plans.isEmpty) return const [];
    final plan = _plans[frameIndex % _plans.length];
    if (plan == null) return const [];
    if (plan.keyImageIndex >= 0) {
      final image = images[plan.keyImageIndex];
      final full = ui.Rect.fromLTWH(
        0,
        0,
        image.width.toDouble(),
        image.height.toDouble(),
      );
      return [LavaTileBlit(plan.keyImageIndex, full, full)];
    }
    return [
      for (final batch in plan.batches)
        for (var i = 0; i < batch.rects.length; i += 4)
          LavaTileBlit(
            batch.imageIndex,
            ui.Rect.fromLTRB(
              batch.rects[i],
              batch.rects[i + 1],
              batch.rects[i + 2],
              batch.rects[i + 3],
            ),
            ui.Rect.fromLTWH(
              batch.transforms[i + 2],
              batch.transforms[i + 3],
              batch.rects[i + 2] - batch.rects[i],
              batch.rects[i + 3] - batch.rects[i + 1],
            ),
          ),
    ];
  }

  /// Returns the full image for [frameIndex], or `null` when the frame cannot
  /// be resolved. Key frames hand back the source image untouched.
  ui.Image? frame(int frameIndex) {
    if (_plans.isEmpty) return null;

    final index = frameIndex % _plans.length;
    final plan = _plans[index];
    if (plan == null) return null;
    if (plan.keyImageIndex >= 0) return images[plan.keyImageIndex];

    final cached = _cache.remove(index);
    if (cached != null) {
      _cache[index] = cached;
      return cached;
    }

    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    for (final batch in plan.batches) {
      canvas.drawRawAtlas(
        images[batch.imageIndex],
        batch.transforms,
        batch.rects,
        null,
        null,
        null,
        _blitPaint,
      );
    }
    final picture = recorder.endRecording();
    final image = picture.toImageSync(manifest.tileWidth, manifest.tileHeight);
    picture.dispose();

    while (_cache.length >= _maxCachedFrames) {
      _cache.remove(_cache.keys.first)!.dispose();
    }
    _cache[index] = image;
    return image;
  }

  static List<_FramePlan?> _compile(
    List<ui.Image> images,
    LavaManifest manifest,
  ) {
    if (images.isEmpty) return const [];

    final contentWidth = manifest.tileWidth.toDouble();
    final contentHeight = manifest.tileHeight.toDouble();
    final cellSize = (manifest.cellSize ?? 32).toDouble();
    final destTilesPerRow = (contentWidth / cellSize).ceil();

    return [
      for (final frameObj in manifest.rawFrames)
        _compileFrame(
          frameObj,
          images,
          contentWidth,
          contentHeight,
          cellSize,
          destTilesPerRow,
        ),
    ];
  }

  static _FramePlan? _compileFrame(
    Object? frameObj,
    List<ui.Image> images,
    double contentWidth,
    double contentHeight,
    double cellSize,
    int destTilesPerRow,
  ) {
    if (frameObj is! Map) return null;

    if (frameObj['type'] == 'key') {
      final imageIndex = (frameObj['imageIndex'] as num?)?.toInt() ?? 0;
      if (imageIndex < 0 || imageIndex >= images.length) return null;
      return _FramePlan.key(imageIndex);
    }

    final diffs = frameObj['diffs'];
    if (diffs is! List) return null;

    // Consecutive blocks from the same image share a batch; a new batch starts
    // whenever the source changes so the manifest's paint order is preserved.
    final batches = <_AtlasBatch>[];
    var batchImage = -1;
    final transforms = <double>[];
    final rects = <double>[];

    void flush() {
      if (rects.isEmpty) return;
      batches.add(
        _AtlasBatch(
          batchImage,
          Float32List.fromList(transforms),
          Float32List.fromList(rects),
        ),
      );
      transforms.clear();
      rects.clear();
    }

    for (final entry in diffs) {
      if (entry is! List || entry.length < 5) continue;

      final srcIndex = (entry[0] as num).toInt();
      if (srcIndex < 0 || srcIndex >= images.length) continue;

      final srcImage = images[srcIndex];
      final srcTileIndex = (entry[1] as num).toInt();
      final destTileIndex = (entry[4] as num).toInt();
      final srcTilesPerRow = (srcImage.width / cellSize).ceil();

      final srcX = (srcTileIndex % srcTilesPerRow) * cellSize;
      final srcY = (srcTileIndex ~/ srcTilesPerRow) * cellSize;
      final dstX = (destTileIndex % destTilesPerRow) * cellSize;
      final dstY = (destTileIndex ~/ destTilesPerRow) * cellSize;

      // Blocks on the right / bottom edge overhang the frame (and the atlas)
      // whenever the size is not a multiple of the cell size.
      final drawW = math.min(
        (entry[2] as num) * cellSize,
        math.min(srcImage.width - srcX, contentWidth - dstX),
      );
      final drawH = math.min(
        (entry[3] as num) * cellSize,
        math.min(srcImage.height - srcY, contentHeight - dstY),
      );
      if (drawW <= 0 || drawH <= 0) continue;

      if (srcIndex != batchImage) {
        flush();
        batchImage = srcIndex;
      }
      // RSTransform (scos, ssin, tx, ty): identity scale, translate to dest.
      transforms.addAll([1.0, 0.0, dstX, dstY]);
      rects.addAll([srcX, srcY, srcX + drawW, srcY + drawH]);
    }
    flush();

    return _FramePlan.diff(batches);
  }

  /// Bytes of RGBA currently held by composed frames.
  int get cachedBytes =>
      _cache.length * manifest.tileWidth * manifest.tileHeight * 4;

  /// Drops the composed frames (they are rebuilt on demand). Call it when the
  /// bundle leaves the screen: a finished loop holds up to [maxCacheBytes].
  void clearCache() => dispose();

  /// Releases the composed frames. The source [images] belong to the bundle.
  void dispose() {
    for (final image in _cache.values) {
      image.dispose();
    }
    _cache.clear();
  }
}

/// One block of tiles copied from a bundle image into a frame.
class LavaTileBlit {
  const LavaTileBlit(this.imageIndex, this.source, this.destination);

  /// Index into the bundle images: 0 is the key frame, 1 the diff atlas.
  final int imageIndex;

  /// Pixels read from that image.
  final ui.Rect source;

  /// Pixels written in the frame.
  final ui.Rect destination;
}

class _FramePlan {
  const _FramePlan.key(this.keyImageIndex) : batches = const [];
  const _FramePlan.diff(this.batches) : keyImageIndex = -1;

  final int keyImageIndex;
  final List<_AtlasBatch> batches;
}

class _AtlasBatch {
  const _AtlasBatch(this.imageIndex, this.transforms, this.rects);

  final int imageIndex;
  final Float32List transforms;
  final Float32List rects;
}
