## 0.1.0

Initial release.

* `LavaIcon` plays OpenLava bundles (`manifest.json` + key frame + diff tile
  atlas) and single grid atlases with a native 32-bit alpha channel, scaled
  with `BoxFit`, optionally tinted, at the display's refresh rate.
* `LavaBundle.openLavaAsset` decodes a bundle once per asset path and shares it
  between every widget showing it; `retain` / `release` free composed frames
  when the last widget leaves, and `evictOpenLavaCache` drops everything.
  AVIF with a WebP `fallbackUrl` is supported, with the fallback preferred on
  native platforms (`LavaBundle.preferFallbackImages`).
* `LavaFrameCompositor` compiles the manifest into typed-data blit plans (one
  `drawRawAtlas` call per source image, no per-frame parsing or allocation),
  composes frames 1:1 so tiles never bleed, and caches a loop whole when it
  fits its byte budget.
* `LavaController`: play, pause, stop, reset, `seekToFrame`, `seekToProgress`,
  variable `speed`, loop bounds (`loopStartFrame` / `loopEndFrame` for
  "intro, then loop" bundles) and `playOnce` for icons that play through once
  when selected. `LavaIcon` reconfigures an external controller from the
  bundle's manifest.
* `LavaInteractive`: hover tilt (perspective `Matrix4`), elastic press bounce,
  light haptics, `dragToRotate` to scrub the frames by hand and
  `scrubOnHover`; playback resumes after a drag.
* `LavaIcon.demo` loads the demo bundles a host app ships under
  `assets/lava/<name>/` (`LavaBundle.demoAssetPaths`), switches to the
  `_hd` variant when painted large, and falls back to the procedural
  `LavaDemoBaker` atlases for the Macintosh and sunflower.
* `tool/`: the Python pipeline used to key, animate, relight, ray-march and
  encode OpenLava bundles (`animate_icon.py`, `relight_icon.py`,
  `sdf_scenes.py` + `lava_sdf.py`, `openlava_encode.py`), with
  `openlava_gif.py` to render a bundle to a GIF.
