import 'package:flutter/material.dart';
import 'package:lava_flutter/lava_flutter.dart';

void main() {
  runApp(const LavaExampleApp());
}

/// The OpenLava bundles this example ships (see `pubspec.yaml`).
const List<({String label, String asset})> kIcons = [
  (label: 'Ball', asset: 'assets/lava/bingo_ball'),
  (label: 'Dice', asset: 'assets/lava/dice'),
  (label: 'Pencil', asset: 'assets/lava/pencil'),
];

class LavaExampleApp extends StatelessWidget {
  const LavaExampleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'lava_flutter example',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: const Color(0xFF2962FF)),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  // Bundles are decoded once per asset path and shared by every widget that
  // shows them, so the hero icon and the tab icon of the same bundle cost one
  // decode.
  late final Future<List<LavaBundle>> _bundles = Future.wait([
    for (final icon in kIcons) LavaBundle.openLavaAsset(assetPath: icon.asset),
  ]);

  // One controller per tab icon: it stays on its first frame until the tab is
  // selected, then plays through once.
  final List<LavaController> _tabControllers = [];
  int _selected = 0;
  int _counter = 0;

  @override
  void dispose() {
    for (final controller in _tabControllers) {
      controller.dispose();
    }
    super.dispose();
  }

  void _onTabSelected(int index) {
    setState(() => _selected = index);
    _tabControllers[index].playOnce();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);

    return FutureBuilder<List<LavaBundle>>(
      future: _bundles,
      builder: (context, snapshot) {
        final bundles = snapshot.data;
        if (bundles == null) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (_tabControllers.isEmpty) {
          for (final bundle in bundles) {
            _tabControllers.add(
              LavaController(
                totalFrames: bundle.manifest.totalFrames,
                fps: bundle.manifest.frameRate,
                autoPlay: false,
              ),
            );
          }
        }

        return Scaffold(
          appBar: AppBar(title: const Text('lava_flutter')),
          body: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // The hero loops and reacts to the pointer: hover tilts it,
                // dragging sideways scrubs its frames.
                LavaIcon(
                  bundle: bundles[_selected],
                  size: 180,
                  interactive: true,
                  autoPlay: !reduceMotion,
                ),
                const SizedBox(height: 24),
                Text(
                  'Hover or drag the icon. Select a tab to play it once.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 24),
                Text(
                  'Button pressed $_counter times',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
          floatingActionButton: FloatingActionButton(
            onPressed: () => setState(() => _counter++),
            tooltip: 'Increment',
            child: const Icon(Icons.add),
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _selected,
            onDestinationSelected: _onTabSelected,
            destinations: [
              for (var i = 0; i < bundles.length; i++)
                NavigationDestination(
                  icon: LavaIcon(
                    bundle: bundles[i],
                    controller: _tabControllers[i],
                    size: 28,
                    autoPlay: false,
                  ),
                  label: kIcons[i].label,
                ),
            ],
          ),
        );
      },
    );
  }
}
