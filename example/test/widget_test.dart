import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lava_flutter/lava_flutter.dart';
import 'package:lava_flutter_example/main.dart';

void main() {
  testWidgets('shows the bundled icons and plays a tab once', (tester) async {
    // Decoding the bundles is real I/O, which the test's fake clock does not
    // drive; the app then picks them up from the loader cache.
    await tester.runAsync(
      () => Future.wait([
        for (final icon in kIcons)
          LavaBundle.openLavaAsset(assetPath: icon.asset),
      ]),
    );

    await tester.pumpWidget(const LavaExampleApp());
    // The cached futures completed in the real zone, so their callbacks run
    // on the real event loop, not the fake clock.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();
    // Let the floating action button finish its entrance animation.
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(LavaIcon), findsNWidgets(4));
    expect(find.text('Button pressed 0 times'), findsOneWidget);

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pump();
    expect(find.text('Button pressed 1 times'), findsOneWidget);

    await tester.tap(find.text('Dice'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    expect(find.byType(NavigationBar), findsOneWidget);
  });
}
