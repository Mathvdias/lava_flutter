import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';

import '../model/lava_types.dart';

/// Manages playback state, timeline scrubbing, and tick synchronization
/// for Lava animations.
class LavaController implements Listenable {
  LavaController({
    required int totalFrames,
    int fps = 30,
    bool loop = true,
    int loopStartFrame = 0,
    int? loopEndFrame,
    bool autoPlay = true,
    double speed = 1.0,
    TickerProvider? vsync,
  }) : _totalFrames = totalFrames,
       _fps = fps,
       _loop = loop,
       _loopStartFrame = loopStartFrame,
       _loopEndFrame = loopEndFrame ?? (totalFrames - 1),
       _speed = speed,
       _statusNotifier = ValueNotifier<LavaPlaybackStatus>(
         autoPlay ? LavaPlaybackStatus.playing : LavaPlaybackStatus.stopped,
       ),
       _currentFrameNotifier = ValueNotifier<int>(0) {
    if (vsync != null) {
      attach(vsync);
      if (autoPlay) {
        play();
      }
    }
  }

  int _totalFrames;
  int _fps;
  bool _loop;
  int _loopStartFrame;
  int _loopEndFrame;

  /// Total number of animation frames.
  int get totalFrames => _totalFrames;

  /// Playback rate in frames per second.
  int get fps => _fps;

  /// Whether the animation loops continuously.
  bool get loop => _loop;

  /// Index of the first frame in the loop section.
  int get loopStartFrame => _loopStartFrame;

  /// Index of the last frame in the loop section (inclusive).
  int get loopEndFrame => _loopEndFrame;

  /// Updates playback bounds and metadata when switching bundles dynamically.
  void configure({
    required int totalFrames,
    int? fps,
    bool? loop,
    int? loopStartFrame,
    int? loopEndFrame,
  }) {
    _totalFrames = totalFrames;
    if (fps != null) _fps = fps;
    if (loop != null) _loop = loop;
    _loopStartFrame = loopStartFrame ?? 0;
    _loopEndFrame = loopEndFrame ?? (totalFrames - 1);
    if (_currentFrameNotifier.value >= totalFrames) {
      _currentFrameNotifier.value = 0;
    }
    _configNotifier.value++;
  }

  // Bumped by [configure] so listeners (timelines, sliders) pick up new bounds.
  final ValueNotifier<int> _configNotifier = ValueNotifier<int>(0);

  double _speed;
  Ticker? _ticker;
  Duration _lastElapsed = Duration.zero;
  double _accumulatedSeconds = 0.0;

  final ValueNotifier<LavaPlaybackStatus> _statusNotifier;
  final ValueNotifier<int> _currentFrameNotifier;

  /// Notifier exposing the current playback status.
  ValueListenable<LavaPlaybackStatus> get statusNotifier => _statusNotifier;

  /// Notifier exposing the currently active zero-indexed frame.
  ValueListenable<int> get currentFrameNotifier => _currentFrameNotifier;

  /// The active frame index.
  int get currentFrame => _currentFrameNotifier.value;

  /// The current playback status.
  LavaPlaybackStatus get status => _statusNotifier.value;

  /// Playback speed multiplier (e.g. 1.0 = normal, 0.5 = half speed, 2.0 = double).
  double get speed => _speed;

  /// Whether the animation is actively ticking.
  bool get isPlaying => _statusNotifier.value == LavaPlaybackStatus.playing;

  /// Whether a [TickerProvider] is currently attached.
  bool get isAttached => _ticker != null;

  /// Attaches a [TickerProvider] to drive playback.
  void attach(TickerProvider vsync) {
    _ticker?.dispose();
    _ticker = vsync.createTicker(_onTick);
    if (_statusNotifier.value == LavaPlaybackStatus.playing) {
      _ticker?.start();
    }
  }

  /// Detaches and disposes the active ticker if attached.
  void detach() {
    _ticker?.dispose();
    _ticker = null;
  }

  void _onTick(Duration elapsed) {
    if (_statusNotifier.value != LavaPlaybackStatus.playing) return;

    if (_lastElapsed == Duration.zero) {
      _lastElapsed = elapsed;
      return;
    }

    final dt = (elapsed - _lastElapsed).inMicroseconds / 1e6;
    _lastElapsed = elapsed;

    _accumulatedSeconds += dt * _speed;
    final frameDurationSec = 1.0 / (fps > 0 ? fps : 30);

    if (_accumulatedSeconds >= frameDurationSec) {
      final framesToAdvance = (_accumulatedSeconds / frameDurationSec).floor();
      _accumulatedSeconds %= frameDurationSec;

      _advanceFrames(framesToAdvance);
    }
  }

  void _advanceFrames(int count) {
    if (totalFrames <= 1) return;

    int next = _currentFrameNotifier.value + count;

    if (loop) {
      final loopRange = (loopEndFrame - loopStartFrame) + 1;
      if (loopRange > 0 && next > loopEndFrame) {
        final overflow = (next - loopEndFrame - 1) % loopRange;
        next = loopStartFrame + overflow;
      }
    } else {
      if (next >= totalFrames - 1) {
        next = totalFrames - 1;
        _currentFrameNotifier.value = next;
        _statusNotifier.value = LavaPlaybackStatus.completed;
        _ticker?.stop();
        return;
      }
    }

    _currentFrameNotifier.value = next.clamp(0, totalFrames - 1);
  }

  /// Starts or resumes playback.
  void play() {
    if (status == LavaPlaybackStatus.completed) {
      seekToFrame(0);
    }
    _statusNotifier.value = LavaPlaybackStatus.playing;
    _lastElapsed = Duration.zero;
    if (_ticker != null && !_ticker!.isActive) {
      _ticker!.start();
    }
  }

  /// Pauses playback at the current frame.
  void pause() {
    _statusNotifier.value = LavaPlaybackStatus.paused;
    _ticker?.stop();
    _lastElapsed = Duration.zero;
  }

  /// Stops playback and rewinds to frame 0.
  void stop() {
    _statusNotifier.value = LavaPlaybackStatus.stopped;
    _ticker?.stop();
    _lastElapsed = Duration.zero;
    _accumulatedSeconds = 0.0;
    _currentFrameNotifier.value = 0;
  }

  /// Resets to the initial frame without changing playback status.
  void reset() {
    _currentFrameNotifier.value = 0;
    _accumulatedSeconds = 0.0;
    _lastElapsed = Duration.zero;
  }

  /// Jumps directly to a specific [frameIndex].
  void seekToFrame(int frameIndex) {
    _currentFrameNotifier.value = frameIndex.clamp(0, totalFrames - 1);
    _accumulatedSeconds = 0.0;
  }

  /// Jumps to normalized timeline position `[0.0, 1.0]`.
  void seekToProgress(double progress) {
    final frame = (progress.clamp(0.0, 1.0) * (totalFrames - 1)).round();
    seekToFrame(frame);
  }

  /// Sets the playback speed multiplier.
  void setSpeed(double newSpeed) {
    if (newSpeed > 0) {
      _speed = newSpeed;
    }
  }

  @override
  void addListener(VoidCallback listener) {
    _currentFrameNotifier.addListener(listener);
    _statusNotifier.addListener(listener);
    _configNotifier.addListener(listener);
  }

  @override
  void removeListener(VoidCallback listener) {
    _currentFrameNotifier.removeListener(listener);
    _statusNotifier.removeListener(listener);
    _configNotifier.removeListener(listener);
  }

  /// Disposes internal tickers and notifiers.
  void dispose() {
    _ticker?.dispose();
    _ticker = null;
    _statusNotifier.dispose();
    _currentFrameNotifier.dispose();
    _configNotifier.dispose();
  }
}
