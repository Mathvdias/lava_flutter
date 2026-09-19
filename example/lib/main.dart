import 'package:flutter/material.dart';
import 'package:lava_flutter/lava_flutter.dart';

void main() {
  runApp(const LavaExampleApp());
}

class LavaExampleApp extends StatelessWidget {
  const LavaExampleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lava Flutter Demo',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFFF385C),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF0F172A),
      ),
      home: const LavaShowcasePage(),
    );
  }
}

class LavaShowcasePage extends StatefulWidget {
  const LavaShowcasePage({super.key});

  @override
  State<LavaShowcasePage> createState() => _LavaShowcasePageState();
}

class _LavaShowcasePageState extends State<LavaShowcasePage> {
  late final LavaController _controller;
  double _speed = 1.0;

  @override
  void initState() {
    super.initState();
    _controller = LavaController(
      totalFrames: 24,
      fps: 30,
      autoPlay: true,
      loop: true,
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Lava 3D Micro-Animations'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 220,
                height: 220,
                decoration: BoxDecoration(
                  color: const Color(0xFF1E293B),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.08),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.4),
                      blurRadius: 24,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                alignment: Alignment.center,
                child: LavaIcon.demo(
                  controller: _controller,
                  size: 140,
                  interactive: true,
                ),
              ),
              const SizedBox(height: 32),
              AnimatedBuilder(
                animation: _controller,
                builder: (context, _) {
                  return Text(
                    'Frame ${_controller.currentFrame + 1} / ${_controller.totalFrames} • ${_controller.status.name.toUpperCase()}',
                    style: const TextStyle(
                      fontSize: 14,
                      fontFamily: 'monospace',
                      color: Color(0xFF94A3B8),
                    ),
                  );
                },
              ),
              const SizedBox(height: 16),
              AnimatedBuilder(
                animation: _controller,
                builder: (context, _) {
                  return Slider(
                    value: _controller.currentFrame.toDouble(),
                    min: 0,
                    max: (_controller.totalFrames - 1).toDouble(),
                    activeColor: const Color(0xFFFF385C),
                    inactiveColor: const Color(0xFF334155),
                    onChanged: (val) {
                      _controller.seekToFrame(val.round());
                    },
                  );
                },
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton.filled(
                    onPressed: () {
                      if (_controller.isPlaying) {
                        _controller.pause();
                      } else {
                        _controller.play();
                      }
                    },
                    icon: AnimatedBuilder(
                      animation: _controller,
                      builder: (context, _) {
                        return Icon(
                          _controller.isPlaying
                              ? Icons.pause
                              : Icons.play_arrow,
                        );
                      },
                    ),
                  ),
                  const SizedBox(width: 12),
                  IconButton.outlined(
                    onPressed: () => _controller.reset(),
                    icon: const Icon(Icons.replay),
                  ),
                  const SizedBox(width: 12),
                  SegmentedButton<double>(
                    segments: const [
                      ButtonSegment(value: 0.5, label: Text('0.5x')),
                      ButtonSegment(value: 1.0, label: Text('1.0x')),
                      ButtonSegment(value: 2.0, label: Text('2.0x')),
                    ],
                    selected: {_speed},
                    onSelectionChanged: (selected) {
                      setState(() {
                        _speed = selected.first;
                        _controller.setSpeed(_speed);
                      });
                    },
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
