import 'dart:ui' as ui;
import 'package:flutter/widgets.dart';

import '../model/lava_manifest.dart';
import 'lava_controller.dart';
import 'lava_frame_compositor.dart';
import 'tile_math.dart';

/// Blits sub-rectangles from a Lava texture atlas to the canvas.
///
/// Driven directly by [LavaController], rendering individual frames
/// with zero heap allocations during the paint cycle.
class LavaPainter extends CustomPainter {
  LavaPainter({
    this.atlas,
    this.images = const [],
    this.compositor,
    required this.manifest,
    required this.controller,
    this.fit = BoxFit.contain,
    this.alignment = Alignment.center,
    this.color,
    this.blendMode = BlendMode.srcIn,
    this.filterQuality = FilterQuality.medium,
  }) : super(repaint: controller);

  /// Hardware texture containing the packed animation frames for grid mode.
  final ui.Image? atlas;

  /// Hardware textures for OpenLava multi-image diff mode.
  final List<ui.Image> images;

  /// Frame assembler for OpenLava mode. Widgets that rebuild the painter pass
  /// a long-lived instance so the composed frame survives rebuilds; when
  /// omitted the painter composes frames on its own.
  final LavaFrameCompositor? compositor;

  LavaFrameCompositor? _ownCompositor;

  LavaFrameCompositor get _effectiveCompositor =>
      compositor ??
      (_ownCompositor ??= LavaFrameCompositor(
        images: images,
        manifest: manifest,
      ));

  /// Dimension and layout metadata for the animation.
  final LavaManifest manifest;

  /// Playback controller providing the active frame index.
  final LavaController controller;

  /// How the animation frame should be inscribed into the render box.
  final BoxFit fit;

  /// Alignment of the frame within the render box.
  final Alignment alignment;

  /// Optional color filter tint applied to the atlas frame.
  final Color? color;

  /// Blend mode used when [color] is specified.
  final BlendMode blendMode;

  /// Filter quality applied when scaling the texture frame.
  final FilterQuality filterQuality;

  final Paint _paint = Paint();

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;

    _paint.filterQuality = filterQuality;
    _paint.isAntiAlias = false;
    if (color != null) {
      _paint.colorFilter = ColorFilter.mode(color!, blendMode);
    } else {
      _paint.colorFilter = null;
    }

    final frameIndex = controller.currentFrame;

    // 1. OpenLava key/diff mode: the compositor hands back the whole frame,
    // so a single filtered blit scales it without tile seams.
    if (manifest.rawFrames.isNotEmpty && images.isNotEmpty) {
      final frameImage = _effectiveCompositor.frame(frameIndex);
      if (frameImage == null) return;

      final contentSize = Size(
        manifest.tileWidth.toDouble(),
        manifest.tileHeight.toDouble(),
      );
      final fitted = applyBoxFit(fit, contentSize, size);
      final src = Alignment.center.inscribe(
        fitted.source,
        Offset.zero & contentSize,
      );
      final dst = alignment.inscribe(fitted.destination, Offset.zero & size);
      canvas.drawImageRect(frameImage, src, dst, _paint);
      return;
    }

    // 2. Standard Grid Atlas mode
    if (atlas == null) return;

    final totalFrames = manifest.totalFrames > 0 ? manifest.totalFrames : 1;
    final effectiveFrame = frameIndex % totalFrames;

    final srcRect = TileMath.getSourceRect(
      frameIndex: effectiveFrame,
      tileWidth: manifest.tileWidth,
      tileHeight: manifest.tileHeight,
      columns: manifest.columns,
    );

    if (srcRect.isEmpty) return;
    if (srcRect.right > atlas!.width || srcRect.bottom > atlas!.height) return;

    final inputSize = Size(
      manifest.tileWidth.toDouble(),
      manifest.tileHeight.toDouble(),
    );
    final fittedSizes = applyBoxFit(fit, inputSize, size);
    final destRect = alignment.inscribe(
      fittedSizes.destination,
      Offset.zero & size,
    );

    canvas.drawImageRect(atlas!, srcRect, destRect, _paint);
  }

  @override
  bool shouldRepaint(covariant LavaPainter oldDelegate) {
    return oldDelegate.atlas != atlas ||
        oldDelegate.images != images ||
        oldDelegate.compositor != compositor ||
        oldDelegate.manifest != manifest ||
        oldDelegate.controller != controller ||
        oldDelegate.fit != fit ||
        oldDelegate.alignment != alignment ||
        oldDelegate.color != color ||
        oldDelegate.blendMode != blendMode ||
        oldDelegate.filterQuality != filterQuality;
  }
}
