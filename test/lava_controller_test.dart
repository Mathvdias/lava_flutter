import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/src/engine/lava_controller.dart';
import 'package:lava_flutter/src/model/lava_types.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LavaController', () {
    late TestVSync vsync;

    setUp(() {
      vsync = const TestVSync();
    });

    test(
      'initializes with default values and stopped status when autoPlay is false',
      () {
        final controller = LavaController(
          totalFrames: 24,
          fps: 30,
          autoPlay: false,
        );

        expect(controller.totalFrames, 24);
        expect(controller.fps, 30);
        expect(controller.currentFrame, 0);
        expect(controller.status, LavaPlaybackStatus.stopped);
        expect(controller.isPlaying, isFalse);
        expect(controller.speed, 1.0);
        expect(controller.loop, isTrue);
        expect(controller.loopStartFrame, 0);
        expect(controller.loopEndFrame, 23);

        controller.dispose();
      },
    );

    test('seekToFrame clamps to valid boundaries', () {
      final controller = LavaController(totalFrames: 10, autoPlay: false);

      controller.seekToFrame(5);
      expect(controller.currentFrame, 5);

      controller.seekToFrame(-3);
      expect(controller.currentFrame, 0);

      controller.seekToFrame(20);
      expect(controller.currentFrame, 9);

      controller.dispose();
    });

    test('seekToProgress maps [0.0, 1.0] to appropriate frame', () {
      final controller = LavaController(totalFrames: 11, autoPlay: false);

      controller.seekToProgress(0.0);
      expect(controller.currentFrame, 0);

      controller.seekToProgress(0.5);
      expect(controller.currentFrame, 5);

      controller.seekToProgress(1.0);
      expect(controller.currentFrame, 10);

      controller.dispose();
    });

    test('status transitions and play/pause/stop/reset', () {
      final controller = LavaController(
        totalFrames: 10,
        autoPlay: false,
        vsync: vsync,
      );

      expect(controller.status, LavaPlaybackStatus.stopped);

      controller.play();
      expect(controller.status, LavaPlaybackStatus.playing);
      expect(controller.isPlaying, isTrue);

      controller.pause();
      expect(controller.status, LavaPlaybackStatus.paused);
      expect(controller.isPlaying, isFalse);

      controller.seekToFrame(4);
      expect(controller.currentFrame, 4);

      controller.reset();
      expect(controller.currentFrame, 0);
      expect(controller.status, LavaPlaybackStatus.paused);

      controller.stop();
      expect(controller.status, LavaPlaybackStatus.stopped);
      expect(controller.currentFrame, 0);

      controller.dispose();
    });

    test('speed modification enforces positive values', () {
      final controller = LavaController(totalFrames: 10, autoPlay: false);

      controller.setSpeed(2.0);
      expect(controller.speed, 2.0);

      controller.setSpeed(0.5);
      expect(controller.speed, 0.5);

      controller.setSpeed(-1.0);
      expect(controller.speed, 0.5);

      controller.setSpeed(0.0);
      expect(controller.speed, 0.5);

      controller.dispose();
    });

    test('notifies listeners on frame or status changes', () {
      final controller = LavaController(totalFrames: 10, autoPlay: false);
      int notificationCount = 0;

      controller.addListener(() {
        notificationCount++;
      });

      controller.seekToFrame(2);
      expect(notificationCount, 1);

      controller.play();
      expect(notificationCount, 2);

      controller.pause();
      expect(notificationCount, 3);

      controller.dispose();
    });
  });
}
