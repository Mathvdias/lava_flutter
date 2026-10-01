# lava_flutter example

A small app showing three OpenLava icons shipped under `assets/lava/`:

* the selected icon loops in the middle of the screen, with hover tilt and
  drag-to-rotate (`LavaIcon(interactive: true)`);
* the navigation bar plays each icon through once when its tab is selected
  (`LavaController.playOnce`);
* playback is left off when the platform asks for reduced motion.

```sh
flutter run
```
