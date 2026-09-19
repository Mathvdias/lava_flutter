import 'dart:math' as math;
import 'package:flutter/painting.dart';

/// Pure mathematical coordinate utility for calculating sub-pixel tile atlas rectangles.
abstract final class TileMath {
  /// Computes the source [Rect] in the texture atlas for the given [frameIndex].
  ///
  /// Columns are zero-indexed and ordered left-to-right, top-to-bottom.
  static Rect getSourceRect({
    required int frameIndex,
    required int tileWidth,
    required int tileHeight,
    required int columns,
  }) {
    if (columns <= 0 || tileWidth <= 0 || tileHeight <= 0) {
      return Rect.zero;
    }

    final safeIndex = math.max(0, frameIndex);
    final col = safeIndex % columns;
    final row = safeIndex ~/ columns;

    return Rect.fromLTWH(
      (col * tileWidth).toDouble(),
      (row * tileHeight).toDouble(),
      tileWidth.toDouble(),
      tileHeight.toDouble(),
    );
  }

  /// Computes the centered destination [Rect] within [containerSize] that
  /// preserves the tile aspect ratio according to the specified [fit].
  static Rect getDestinationRect({
    required Size containerSize,
    required double tileWidth,
    required double tileHeight,
    BoxFit fit = BoxFit.contain,
  }) {
    if (containerSize.isEmpty || tileWidth <= 0 || tileHeight <= 0) {
      return Rect.zero;
    }

    final inputSize = Size(tileWidth, tileHeight);
    final fittedSizes = applyBoxFit(fit, inputSize, containerSize);

    final dx = (containerSize.width - fittedSizes.destination.width) / 2.0;
    final dy = (containerSize.height - fittedSizes.destination.height) / 2.0;

    return Rect.fromLTWH(
      dx,
      dy,
      fittedSizes.destination.width,
      fittedSizes.destination.height,
    );
  }

  /// Calculates the zero-indexed frame corresponding to a normalized progress `[0.0, 1.0]`.
  static int frameAtProgress({
    required double progress,
    required int totalFrames,
    bool loop = true,
  }) {
    if (totalFrames <= 1) return 0;

    final normalized = loop ? (progress % 1.0) : progress.clamp(0.0, 1.0);
    final frame = (normalized * totalFrames).floor();
    return frame.clamp(0, totalFrames - 1);
  }

  /// Calculates normalized progress `[0.0, 1.0]` corresponding to a frame index.
  static double progressAtFrame({
    required int frameIndex,
    required int totalFrames,
  }) {
    if (totalFrames <= 1) return 0.0;
    return (frameIndex.clamp(0, totalFrames - 1) / (totalFrames - 1)).clamp(
      0.0,
      1.0,
    );
  }
}
