import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../engine/lava_controller.dart';
import '../model/lava_types.dart';

/// Wraps a widget with tactile 3D perspective tilt, horizontal rotation drag,
/// hover tracking, and spring compression physics.
class LavaInteractive extends StatefulWidget {
  const LavaInteractive({
    super.key,
    required this.child,
    this.controller,
    this.maxTiltAngle = 0.20,
    this.pressedScale = 0.94,
    this.returnDuration = const Duration(milliseconds: 240),
    this.bounceDuration = const Duration(milliseconds: 320),
    this.perspective = 0.0012,
    this.enableTilt = true,
    this.enableBounce = true,
    this.enableHaptics = true,
    this.dragToRotate = true,
    this.scrubOnHover = false,
    this.onTap,
    this.onStateChanged,
  });

  /// The child widget to transform.
  final Widget child;

  /// Optional [LavaController] to drive frame rotation via drag or hover.
  final LavaController? controller;

  /// Maximum angular rotation in radians during hover tilt.
  final double maxTiltAngle;

  /// Scale factor applied while the user is actively pressing.
  final double pressedScale;

  /// Duration to return tilt and frames to origin when pointer exits.
  final Duration returnDuration;

  /// Duration of the elastic spring release animation.
  final Duration bounceDuration;

  /// Depth coefficient applied to the 3D projection matrix.
  final double perspective;

  /// Whether pointer hover tilts the 3D perspective.
  final bool enableTilt;

  /// Whether tap interactions produce elastic scale bounce.
  final bool enableBounce;

  /// Whether to invoke light haptic feedback on touch down.
  final bool enableHaptics;

  /// Whether dragging or panning horizontally rotates the 3D model.
  final bool dragToRotate;

  /// Whether moving the cursor over the widget tilts and turns the 3D model toward the cursor.
  final bool scrubOnHover;

  /// Callback fired when the interactive surface is tapped.
  final VoidCallback? onTap;

  /// Callback fired when [LavaInteractiveState] transitions.
  final ValueChanged<LavaInteractiveState>? onStateChanged;

  @override
  State<LavaInteractive> createState() => _LavaInteractiveState();
}

class _LavaInteractiveState extends State<LavaInteractive>
    with TickerProviderStateMixin {
  late final AnimationController _bounceController;
  late final Animation<double> _scaleAnimation;

  late final AnimationController _tiltReturnController;
  Animation<Offset>? _tiltReturnAnimation;

  late final AnimationController _frameReturnController;
  Animation<double>? _frameReturnAnimation;

  Offset _currentTilt = Offset.zero;
  bool _isHovered = false;
  bool _isDragging = false;
  bool _resumeAfterDrag = false;
  double _dragAccumulator = 0.0;
  int _dragStartFrame = 0;
  LavaInteractiveState _state = LavaInteractiveState.idle;

  @override
  void initState() {
    super.initState();

    _bounceController = AnimationController(
      vsync: this,
      duration: widget.bounceDuration,
      value: 1.0,
    );

    _scaleAnimation = CurvedAnimation(
      parent: _bounceController,
      curve: Curves.easeOutBack,
    );

    _tiltReturnController = AnimationController(
      vsync: this,
      duration: widget.returnDuration,
    )..addListener(() {
      if (_tiltReturnAnimation != null) {
        setState(() {
          _currentTilt = _tiltReturnAnimation!.value;
        });
      }
    });

    _frameReturnController = AnimationController(
      vsync: this,
      duration: widget.returnDuration,
    )..addListener(() {
      if (_frameReturnAnimation != null && widget.controller != null) {
        final total = widget.controller!.totalFrames;
        final f =
            (_frameReturnAnimation!.value.round() % total + total) % total;
        widget.controller!.seekToFrame(f);
      }
    });
  }

  @override
  void dispose() {
    _bounceController.dispose();
    _tiltReturnController.dispose();
    _frameReturnController.dispose();
    super.dispose();
  }

  void _updateState(LavaInteractiveState newState) {
    if (_state != newState) {
      _state = newState;
      widget.onStateChanged?.call(newState);
    }
  }

  void _onPointerHover(PointerHoverEvent event, BoxConstraints constraints) {
    if (constraints.maxWidth == 0 || constraints.maxHeight == 0) {
      return;
    }

    final localPos = event.localPosition;
    final normalizedX = ((localPos.dx / constraints.maxWidth) * 2.0 - 1.0)
        .clamp(-1.0, 1.0);
    final normalizedY = ((localPos.dy / constraints.maxHeight) * 2.0 - 1.0)
        .clamp(-1.0, 1.0);

    if (widget.enableTilt) {
      setState(() {
        _currentTilt = Offset(normalizedX, normalizedY);
      });
    }

    if (widget.scrubOnHover &&
        widget.controller != null &&
        !widget.controller!.isPlaying &&
        !_isDragging) {
      final total = widget.controller!.totalFrames;
      final maxOffset = (total / 4.0).round(); // ±90 degree rotation
      final offset = (normalizedX * maxOffset).round();
      final targetFrame = (offset % total + total) % total;
      widget.controller!.seekToFrame(targetFrame);
    }
  }

  void _onPointerEnter(PointerEnterEvent event) {
    _isHovered = true;
    _tiltReturnController.stop();
    _frameReturnController.stop();
    _updateState(LavaInteractiveState.hover);
  }

  void _onPointerExit(PointerExitEvent event) {
    _isHovered = false;
    _updateState(LavaInteractiveState.idle);

    if (widget.enableTilt && _currentTilt != Offset.zero) {
      _tiltReturnAnimation = Tween<Offset>(
        begin: _currentTilt,
        end: Offset.zero,
      ).animate(
        CurvedAnimation(
          parent: _tiltReturnController,
          curve: Curves.easeOutCubic,
        ),
      );
      _tiltReturnController.forward(from: 0.0);
    }

    if (widget.scrubOnHover &&
        widget.controller != null &&
        !widget.controller!.isPlaying &&
        !_isDragging) {
      _animateFrameToRest();
    }
  }

  void _animateFrameToRest() {
    final current = widget.controller!.currentFrame;
    if (current == 0) return;

    final total = widget.controller!.totalFrames;
    int diff = current;
    if (diff > total / 2) {
      diff = diff - total;
    }

    _frameReturnAnimation = Tween<double>(
      begin: diff.toDouble(),
      end: 0.0,
    ).animate(
      CurvedAnimation(
        parent: _frameReturnController,
        curve: Curves.easeOutCubic,
      ),
    );
    _frameReturnController.forward(from: 0.0);
  }

  void _onPanStart(DragStartDetails details) {
    if (widget.controller == null || !widget.dragToRotate) return;
    _isDragging = true;
    _dragAccumulator = 0.0;
    _dragStartFrame = widget.controller!.currentFrame;
    _tiltReturnController.stop();
    _frameReturnController.stop();
    _resumeAfterDrag = widget.controller!.isPlaying;
    if (_resumeAfterDrag) {
      widget.controller!.pause();
    }
    _updateState(LavaInteractiveState.pressed);
    setState(() {});
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (widget.controller == null || !widget.dragToRotate) return;
    _dragAccumulator += details.delta.dx;

    // Smooth weighted rotation: 20 pixels per frame (480px = full 360 degree turn)
    const pixelsPerFrame = 20.0;
    final frameDelta = (_dragAccumulator / pixelsPerFrame).round();
    final total = widget.controller!.totalFrames;
    final target = ((_dragStartFrame + frameDelta) % total + total) % total;
    if (widget.controller!.currentFrame != target) {
      widget.controller!.seekToFrame(target);
    }
  }

  void _onPanEnd(DragEndDetails details) => _endDrag();

  void _endDrag() {
    _isDragging = false;
    // Playback was only suspended for the scrub: carry on from the frame the
    // user left the model at.
    if (_resumeAfterDrag) {
      _resumeAfterDrag = false;
      widget.controller?.play();
    }
    _updateState(
      _isHovered ? LavaInteractiveState.hover : LavaInteractiveState.idle,
    );
    setState(() {});
  }

  void _onTapDown(TapDownDetails details) {
    _updateState(LavaInteractiveState.pressed);

    if (widget.enableHaptics) {
      HapticFeedback.lightImpact();
    }

    if (widget.enableBounce) {
      _bounceController.animateTo(
        widget.pressedScale,
        duration: const Duration(milliseconds: 100),
        curve: Curves.easeOut,
      );
    }
  }

  void _onTapUp(TapUpDetails details) {
    _handleRelease();
    widget.onTap?.call();
  }

  void _onTapCancel() {
    _handleRelease();
  }

  void _handleRelease() {
    _updateState(
      _isHovered ? LavaInteractiveState.hover : LavaInteractiveState.idle,
    );

    if (widget.enableBounce) {
      _bounceController.animateTo(
        1.0,
        duration: widget.bounceDuration,
        curve: Curves.elasticOut,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return MouseRegion(
          onEnter: _onPointerEnter,
          onHover: (e) => _onPointerHover(e, constraints),
          onExit: _onPointerExit,
          cursor:
              _isDragging
                  ? SystemMouseCursors.grabbing
                  : (widget.dragToRotate
                      ? SystemMouseCursors.grab
                      : (widget.onTap != null
                          ? SystemMouseCursors.click
                          : MouseCursor.defer)),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onPanStart: widget.dragToRotate ? _onPanStart : null,
            onPanUpdate: widget.dragToRotate ? _onPanUpdate : null,
            onPanEnd: widget.dragToRotate ? _onPanEnd : null,
            onPanCancel: widget.dragToRotate ? _endDrag : null,
            onTapDown: _onTapDown,
            onTapUp: _onTapUp,
            onTapCancel: _onTapCancel,
            child: AnimatedBuilder(
              animation: _scaleAnimation,
              builder: (context, child) {
                final tiltX =
                    widget.enableTilt
                        ? -_currentTilt.dy * widget.maxTiltAngle
                        : 0.0;
                final tiltY =
                    widget.enableTilt
                        ? _currentTilt.dx * widget.maxTiltAngle
                        : 0.0;

                final s = _scaleAnimation.value;
                final matrix =
                    Matrix4.identity()
                      ..setEntry(3, 2, widget.perspective)
                      ..rotateX(tiltX)
                      ..rotateY(tiltY)
                      ..scaleByDouble(s, s, 1.0, 1.0);

                return Transform(
                  transform: matrix,
                  alignment: Alignment.center,
                  child: child,
                );
              },
              child: widget.child,
            ),
          ),
        );
      },
    );
  }
}
