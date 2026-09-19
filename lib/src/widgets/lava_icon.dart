import 'package:flutter/widgets.dart';

import '../engine/lava_controller.dart';
import '../engine/lava_painter.dart';
import '../loader/lava_bundle.dart';
import '../model/lava_types.dart';
import 'lava_interactive.dart';

/// Renders a high-performance tile-based Lava animation with optional
/// tactile 3D interactivity, drag rotation, and zero-allocation paint loops.
class LavaIcon extends StatefulWidget {
  /// Creates a [LavaIcon] using a preloaded [LavaBundle].
  const LavaIcon({
    super.key,
    required LavaBundle this.bundle,
    this.controller,
    this.size,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.alignment = Alignment.center,
    this.color,
    this.blendMode = BlendMode.srcIn,
    this.filterQuality = FilterQuality.medium,
    this.interactive = false,
    this.autoPlay,
    this.dragToRotate = true,
    this.scrubOnHover = false,
    this.onTap,
    this.onStateChanged,
    this.foregroundPainter,
    this.onBundleChanged,
  }) : demoType = LavaDemoType.macintosh,
       _isDemo = false,
       _imageAsset = null,
       _manifestAsset = null,
       _assetBundle = null;

  /// Creates a [LavaIcon] rendering one of the built-in demo bundles (see [LavaDemoType]).
  const LavaIcon.demo({
    super.key,
    this.demoType = LavaDemoType.macintosh,
    this.controller,
    this.size,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.alignment = Alignment.center,
    this.color,
    this.blendMode = BlendMode.srcIn,
    this.filterQuality = FilterQuality.medium,
    this.interactive = false,
    this.autoPlay,
    this.dragToRotate = true,
    this.scrubOnHover = false,
    this.onTap,
    this.onStateChanged,
    this.foregroundPainter,
    this.onBundleChanged,
    AssetBundle? assetBundle,
  }) : bundle = null,
       _isDemo = true,
       _imageAsset = null,
       _manifestAsset = null,
       _assetBundle = assetBundle;

  /// Creates a [LavaIcon] rendering the built-in sunflower demo bundle.
  const LavaIcon.demoSunflower({
    super.key,
    this.controller,
    this.size,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.alignment = Alignment.center,
    this.color,
    this.blendMode = BlendMode.srcIn,
    this.filterQuality = FilterQuality.medium,
    this.interactive = false,
    this.autoPlay,
    this.dragToRotate = true,
    this.scrubOnHover = false,
    this.onTap,
    this.onStateChanged,
    this.foregroundPainter,
    this.onBundleChanged,
    AssetBundle? assetBundle,
  }) : bundle = null,
       demoType = LavaDemoType.sunflower,
       _isDemo = true,
       _imageAsset = null,
       _manifestAsset = null,
       _assetBundle = assetBundle;

  /// Creates a [LavaIcon] rendering the built-in 3D procedural nature tree animation.
  const LavaIcon.demoTree({
    super.key,
    this.controller,
    this.size,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.alignment = Alignment.center,
    this.color,
    this.blendMode = BlendMode.srcIn,
    this.filterQuality = FilterQuality.medium,
    this.interactive = false,
    this.autoPlay,
    this.dragToRotate = true,
    this.scrubOnHover = false,
    this.onTap,
    this.onStateChanged,
    this.foregroundPainter,
    this.onBundleChanged,
    AssetBundle? assetBundle,
  }) : bundle = null,
       demoType = LavaDemoType.sunflower,
       _isDemo = true,
       _imageAsset = null,
       _manifestAsset = null,
       _assetBundle = assetBundle;

  /// Creates a [LavaIcon] by loading assets asynchronously.
  const LavaIcon.asset({
    super.key,
    required String imageAsset,
    required String manifestAsset,
    AssetBundle? assetBundle,
    this.controller,
    this.size,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.alignment = Alignment.center,
    this.color,
    this.blendMode = BlendMode.srcIn,
    this.filterQuality = FilterQuality.medium,
    this.interactive = false,
    this.autoPlay,
    this.dragToRotate = true,
    this.scrubOnHover = false,
    this.onTap,
    this.onStateChanged,
    this.foregroundPainter,
    this.onBundleChanged,
  }) : bundle = null,
       demoType = LavaDemoType.macintosh,
       _isDemo = false,
       _imageAsset = imageAsset,
       _manifestAsset = manifestAsset,
       _assetBundle = assetBundle;

  /// The preloaded bundle containing atlas texture and manifest metadata.
  final LavaBundle? bundle;

  /// Optional playback controller. If omitted, an internal controller is created.
  final LavaController? controller;

  /// Shorthand dimension setting both width and height equally.
  final double? size;

  /// Explicit width of the rendered icon box.
  final double? width;

  /// Explicit height of the rendered icon box.
  final double? height;

  /// Scaling mode applied when mapping frames to the widget boundaries.
  final BoxFit fit;

  /// Alignment of the frame within the render box.
  final Alignment alignment;

  /// Optional color filter tint.
  final Color? color;

  /// Blend mode for the color tint filter.
  final BlendMode blendMode;

  /// Filtering quality when scaling texture frames.
  final FilterQuality filterQuality;

  /// Whether to enable tactile 3D perspective tilt and spring compression.
  final bool interactive;

  /// Whether to automatically play the animation loop continuously.
  /// When [interactive] is true, defaults to `false` so the user can interact
  /// with the model directly via touch or drag.
  final bool? autoPlay;

  /// Whether horizontal dragging rotates the 3D model 360 degrees.
  final bool dragToRotate;

  /// Whether cursor hover tilts and tracks the 3D model toward the pointer.
  final bool scrubOnHover;

  /// Callback executed when tapped.
  final VoidCallback? onTap;

  /// Callback fired when interactive state transitions.
  final ValueChanged<LavaInteractiveState>? onStateChanged;

  /// The procedural 3D model variant when rendering demo icons.
  final LavaDemoType demoType;

  final bool _isDemo;
  final String? _imageAsset;
  final String? _manifestAsset;
  final AssetBundle? _assetBundle;

  /// Painted over the animation, inside the same tilt / bounce transform
  /// (debug overlays, badges). Its canvas is the icon's box.
  final CustomPainter? foregroundPainter;

  /// Called whenever a different bundle goes on screen (first load, a new demo
  /// type, the swap from the standard to the large-preview variant).
  final ValueChanged<LavaBundle>? onBundleChanged;

  @override
  State<LavaIcon> createState() => _LavaIconState();
}

class _LavaIconState extends State<LavaIcon> with TickerProviderStateMixin {
  LavaBundle? _bundle;
  // Only bundles decoded by LavaIcon.asset belong to this widget; demo
  // bundles are shared through the loader caches and injected ones belong to
  // the caller.
  bool _ownsBundle = false;
  LavaController? _internalController;
  bool _isLoading = false;
  int _loadGeneration = 0;
  bool _didStart = false;
  bool _useHd = false;

  LavaController get _effectiveController {
    if (widget.controller != null) return widget.controller!;
    return _internalController!;
  }

  bool get _effectiveAutoPlay {
    if (widget.autoPlay != null) return widget.autoPlay!;
    return !widget.interactive;
  }

  @override
  void initState() {
    super.initState();
    if (widget.bundle != null) {
      _setBundle(widget.bundle!);
      _initControllerIfNeeded();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final upgraded = _upgradeToHdIfNeeded();
    if (!_didStart) {
      _didStart = true;
      if (widget.bundle == null) _loadBundleAsync();
    } else if (upgraded && widget.bundle == null) {
      _loadBundleAsync();
    }
  }

  /// A demo icon painted well above the standard bundle's resolution switches
  /// to the large-preview bundle. It never switches back: resizing a window
  /// around the threshold must not reload the icon over and over.
  bool _upgradeToHdIfNeeded() {
    if (_useHd || !widget._isDemo) return false;
    final logicalWidth = widget.width ?? widget.size ?? 64.0;
    final pixelRatio = MediaQuery.maybeDevicePixelRatioOf(context) ?? 1.0;
    _useHd = logicalWidth * pixelRatio > LavaBundle.demoBaseWidth * 1.35;
    return _useHd;
  }

  void _showBundle(LavaBundle bundle, {required bool owned}) {
    if (identical(bundle, _bundle)) return;
    if (bundle.isDisposed) {
      // Its last user let go between our request and now: load it again.
      _loadBundleAsync();
      return;
    }
    final frame = _internalController?.currentFrame ?? 0;
    setState(() {
      _setBundle(bundle, owned: owned);
      _isLoading = false;
    });
    _initControllerIfNeeded();
    widget.onBundleChanged?.call(bundle);
    // Both variants are the same animation: carry the playhead over so the
    // swap to the large one is not a visible restart.
    if (frame > 0 && frame < bundle.manifest.totalFrames) {
      _internalController?.seekToFrame(frame);
    }
  }

  void _setBundle(LavaBundle bundle, {bool owned = false}) {
    if (identical(_bundle, bundle)) return;
    final previous = _bundle;
    bundle.retain();
    _bundle = bundle;
    if (_ownsBundle) {
      previous?.dispose();
    } else {
      previous?.release();
    }
    _ownsBundle = owned;
  }

  @override
  void didUpdateWidget(covariant LavaIcon oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.bundle != oldWidget.bundle && widget.bundle != null) {
      _loadGeneration++;
      _setBundle(widget.bundle!);
      _initControllerIfNeeded();
    } else if (widget._isDemo &&
        (widget.demoType != oldWidget.demoType || _upgradeToHdIfNeeded())) {
      _loadBundleAsync();
    } else if (widget.controller != oldWidget.controller &&
        widget.controller != null &&
        _bundle != null) {
      _initControllerIfNeeded();
    } else if (_effectiveAutoPlay !=
        (oldWidget.autoPlay ?? !oldWidget.interactive)) {
      if (widget.controller != null) {
        if (_effectiveAutoPlay && !widget.controller!.isPlaying) {
          widget.controller!.play();
        } else if (!_effectiveAutoPlay && widget.controller!.isPlaying) {
          widget.controller!.pause();
        }
      } else if (_internalController != null) {
        if (_effectiveAutoPlay) {
          _internalController!.play();
        } else {
          _internalController!.pause();
          _internalController!.reset();
        }
      }
    }
  }

  Future<void> _loadBundleAsync() async {
    // A slower load started for a previous demo type must not overwrite this one.
    final generation = ++_loadGeneration;
    // The current bundle stays on screen until the next one is decoded.
    setState(() {
      _isLoading = _bundle == null;
    });

    try {
      if (widget._isDemo && _useHd) {
        // Progressive: the standard bundle is small (and usually already
        // decoded for a thumbnail), so it goes on screen at once; the large
        // variant replaces it when its atlas is ready.
        final standard = await LavaBundle.demo(
          type: widget.demoType,
          bundle: widget._assetBundle,
        );
        if (!mounted || generation != _loadGeneration) return;
        _showBundle(standard, owned: false);
      }

      final loadedBundle =
          widget._isDemo
              ? await LavaBundle.demo(
                type: widget.demoType,
                hd: _useHd,
                bundle: widget._assetBundle,
              )
              : await LavaBundle.fromAsset(
                imageAsset: widget._imageAsset!,
                manifestAsset: widget._manifestAsset!,
                bundle: widget._assetBundle,
              );

      if (!mounted || generation != _loadGeneration) {
        if (!widget._isDemo) loadedBundle.dispose();
        return;
      }
      _showBundle(loadedBundle, owned: !widget._isDemo);
    } catch (error, stackTrace) {
      // A missing or corrupt bundle leaves the placeholder box; report it
      // instead of failing silently.
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stackTrace,
          library: 'lava_flutter',
          context: ErrorDescription('while loading a LavaIcon bundle'),
        ),
      );
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _initControllerIfNeeded() {
    if (widget.controller == null && _bundle != null) {
      _internalController?.dispose();
      _internalController = LavaController(
        totalFrames: _bundle!.manifest.totalFrames,
        fps: _bundle!.manifest.frameRate,
        loop: _bundle!.manifest.loop,
        loopStartFrame: _bundle!.manifest.loopStartFrame,
        loopEndFrame: _bundle!.manifest.loopEndFrame,
        autoPlay: _effectiveAutoPlay,
        vsync: this,
      );
    } else if (widget.controller != null && _bundle != null) {
      if (!widget.controller!.isAttached) {
        widget.controller!.attach(this);
      }
      widget.controller!.configure(
        totalFrames: _bundle!.manifest.totalFrames,
        fps: _bundle!.manifest.frameRate,
        loop: _bundle!.manifest.loop,
        loopStartFrame: _bundle!.manifest.loopStartFrame,
        loopEndFrame: _bundle!.manifest.loopEndFrame,
      );
      if (widget.autoPlay == true && !widget.controller!.isPlaying) {
        widget.controller!.play();
      }
    }
  }

  @override
  void dispose() {
    _internalController?.dispose();
    if (_ownsBundle) {
      _bundle?.dispose();
    } else {
      _bundle?.release();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final effectiveWidth = widget.width ?? widget.size ?? 64.0;
    final effectiveHeight = widget.height ?? widget.size ?? 64.0;

    if (_isLoading || _bundle == null) {
      return SizedBox(width: effectiveWidth, height: effectiveHeight);
    }

    Widget content = RepaintBoundary(
      child: CustomPaint(
        size: Size(effectiveWidth, effectiveHeight),
        foregroundPainter: widget.foregroundPainter,
        painter: LavaPainter(
          atlas: _bundle!.atlas,
          images: _bundle!.images,
          compositor: _bundle!.compositor,
          manifest: _bundle!.manifest,
          controller: _effectiveController,
          fit: widget.fit,
          alignment: widget.alignment,
          color: widget.color,
          blendMode: widget.blendMode,
          filterQuality: widget.filterQuality,
        ),
      ),
    );

    if (widget.interactive) {
      content = LavaInteractive(
        controller: _effectiveController,
        dragToRotate: widget.dragToRotate,
        scrubOnHover: widget.scrubOnHover,
        onTap: widget.onTap,
        onStateChanged: widget.onStateChanged,
        child: content,
      );
    }

    return SizedBox(
      width: effectiveWidth,
      height: effectiveHeight,
      child: content,
    );
  }
}
