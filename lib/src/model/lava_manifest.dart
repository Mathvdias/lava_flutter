/// Metadata and coordinate specifications for a tile-based Lava animation.
class LavaManifest {
  const LavaManifest({
    required this.tileWidth,
    required this.tileHeight,
    required this.columns,
    required this.rows,
    required this.totalFrames,
    this.version = 1,
    this.frameRate = 30,
    this.loop = true,
    this.loopStartFrame = 0,
    int? loopEndFrame,
    this.cellSize,
    this.diffImageSize,
    this.alpha = true,
    this.images = const [],
    this.imageFallbacks = const [],
    this.rawFrames = const [],
  }) : loopEndFrame = loopEndFrame ?? (totalFrames - 1);

  /// Schema version identifier.
  final int version;

  /// Target playback frame rate (e.g. 30, 60).
  final int frameRate;

  /// Width in pixels of each individual animation tile frame.
  final int tileWidth;

  /// Height in pixels of each individual animation tile frame.
  final int tileHeight;

  /// Number of columns in the tile atlas grid.
  final int columns;

  /// Number of rows in the tile atlas grid.
  final int rows;

  /// Total count of frames in the sequence.
  final int totalFrames;

  /// Whether the animation loops continuously.
  final bool loop;

  /// Starting frame index for loop iterations (zero-indexed).
  final int loopStartFrame;

  /// Ending frame index for loop iterations (inclusive).
  final int loopEndFrame;

  /// Cell / tile size in pixels (OpenLava specification).
  final int? cellSize;

  /// Width / height of diff tileset in pixels (OpenLava specification).
  final int? diffImageSize;

  /// Whether alpha transparency is enabled (OpenLava specification).
  final bool alpha;

  /// Relative URLs or identifiers of atlas images (OpenLava specification).
  final List<String> images;

  /// Alternative file per entry of [images] (`fallbackUrl` in the manifest),
  /// used when the platform cannot decode the primary one (an AVIF atlas on a
  /// system without an AV1 decoder). Empty or `null` entries mean no fallback.
  final List<String?> imageFallbacks;

  /// Raw frames metadata list (OpenLava specification).
  final List<dynamic> rawFrames;

  /// Duration of a single frame based on the configured [frameRate].
  Duration get frameDuration {
    final effectiveFps = frameRate > 0 ? frameRate : 30;
    return Duration(microseconds: (1000000 / effectiveFps).round());
  }

  /// Total duration of one complete playback sequence.
  Duration get totalDuration => frameDuration * totalFrames;

  /// Parses a [LavaManifest] from either an OpenLava or standard Grid Atlas JSON map.
  factory LavaManifest.fromJson(Map<String, dynamic> json) {
    final rawFramesList =
        (json['frames'] is List)
            ? (json['frames'] as List<dynamic>)
            : const <dynamic>[];
    final hasOpenLavaFrames = rawFramesList.isNotEmpty;

    final fps =
        (json['fps'] as num?)?.toInt() ??
        (json['frameRate'] as num?)?.toInt() ??
        30;

    final tileWidth =
        (json['tileWidth'] as num?)?.toInt() ??
        (json['width'] as num?)?.toInt() ??
        64;
    final tileHeight =
        (json['tileHeight'] as num?)?.toInt() ??
        (json['height'] as num?)?.toInt() ??
        64;

    final columns =
        (json['columns'] as num?)?.toInt() ?? (hasOpenLavaFrames ? 1 : 6);
    final rows =
        (json['rows'] as num?)?.toInt() ??
        (hasOpenLavaFrames ? rawFramesList.length : 4);

    final totalFrames =
        (json['totalFrames'] as num?)?.toInt() ??
        (hasOpenLavaFrames ? rawFramesList.length : (columns * rows));

    final imagesList = <String>[];
    final fallbackList = <String?>[];
    if (json['images'] is List) {
      for (final item in json['images'] as List) {
        if (item is Map && item['url'] is String) {
          imagesList.add(item['url'] as String);
          fallbackList.add(item['fallbackUrl'] as String?);
        } else if (item is String) {
          imagesList.add(item);
          fallbackList.add(null);
        }
      }
    }

    return LavaManifest(
      version: (json['version'] as num?)?.toInt() ?? 1,
      frameRate: fps,
      tileWidth: tileWidth,
      tileHeight: tileHeight,
      columns: columns,
      rows: rows,
      totalFrames: totalFrames,
      loop: json['loop'] as bool? ?? true,
      loopStartFrame: (json['loopStartFrame'] as num?)?.toInt() ?? 0,
      loopEndFrame:
          (json['loopEndFrame'] as num?)?.toInt() ?? (totalFrames - 1),
      cellSize: (json['cellSize'] as num?)?.toInt(),
      diffImageSize: (json['diffImageSize'] as num?)?.toInt(),
      alpha: json['alpha'] as bool? ?? true,
      images: imagesList,
      imageFallbacks: fallbackList,
      rawFrames: rawFramesList,
    );
  }

  /// Serializes the manifest into a JSON map.
  Map<String, dynamic> toJson() => {
    'version': version,
    'frameRate': frameRate,
    'tileWidth': tileWidth,
    'tileHeight': tileHeight,
    'columns': columns,
    'rows': rows,
    'totalFrames': totalFrames,
    'loop': loop,
    'loopStartFrame': loopStartFrame,
    'loopEndFrame': loopEndFrame,
    if (cellSize != null) 'cellSize': cellSize,
    if (diffImageSize != null) 'diffImageSize': diffImageSize,
    'alpha': alpha,
    if (images.isNotEmpty)
      'images': [
        for (var i = 0; i < images.length; i++)
          {
            'url': images[i],
            if (i < imageFallbacks.length && imageFallbacks[i] != null)
              'fallbackUrl': imageFallbacks[i],
          },
      ],
  };

  LavaManifest copyWith({
    int? version,
    int? frameRate,
    int? tileWidth,
    int? tileHeight,
    int? columns,
    int? rows,
    int? totalFrames,
    bool? loop,
    int? loopStartFrame,
    int? loopEndFrame,
  }) {
    return LavaManifest(
      version: version ?? this.version,
      frameRate: frameRate ?? this.frameRate,
      tileWidth: tileWidth ?? this.tileWidth,
      tileHeight: tileHeight ?? this.tileHeight,
      columns: columns ?? this.columns,
      rows: rows ?? this.rows,
      totalFrames: totalFrames ?? this.totalFrames,
      loop: loop ?? this.loop,
      loopStartFrame: loopStartFrame ?? this.loopStartFrame,
      loopEndFrame: loopEndFrame ?? this.loopEndFrame,
      cellSize: cellSize,
      diffImageSize: diffImageSize,
      alpha: alpha,
      images: images,
      imageFallbacks: imageFallbacks,
      rawFrames: rawFrames,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is LavaManifest &&
          runtimeType == other.runtimeType &&
          version == other.version &&
          frameRate == other.frameRate &&
          tileWidth == other.tileWidth &&
          tileHeight == other.tileHeight &&
          columns == other.columns &&
          rows == other.rows &&
          totalFrames == other.totalFrames &&
          loop == other.loop &&
          loopStartFrame == other.loopStartFrame &&
          loopEndFrame == other.loopEndFrame &&
          cellSize == other.cellSize &&
          diffImageSize == other.diffImageSize &&
          alpha == other.alpha &&
          _sameList(images, other.images) &&
          _sameList(imageFallbacks, other.imageFallbacks) &&
          // Frame lists are parsed JSON: two manifests share them or differ.
          (identical(rawFrames, other.rawFrames) ||
              (rawFrames.isEmpty && other.rawFrames.isEmpty));

  static bool _sameList(List<Object?> a, List<Object?> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hash(
    version,
    frameRate,
    tileWidth,
    tileHeight,
    columns,
    rows,
    totalFrames,
    loop,
    loopStartFrame,
    loopEndFrame,
  );
}
