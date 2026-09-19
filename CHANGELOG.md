## 0.2.0

* Built-in demo icons (`LavaDemoType.macintosh`, `LavaDemoType.sunflower`,
  `LavaDemoType.lavaLamp`, `LavaDemoType.campfire`, `LavaDemoType.rocket`,
  `LavaDemoType.senna`, `LavaDemoType.christmasTree`) are real OpenLava diff tilesets
  (3D-rendered key frame + 32px diff atlas + manifest). The procedural Canvas renderer stays
  available through `LavaBundle.procedural` for offline fallbacks.
* `LavaBundle.demoAssetPaths` maps every demo type to its asset directory.
* `LavaIcon` reconfigures an externally supplied `LavaController` from the decoded bundle
  manifest (frame count, fps, loop bounds) when they do not match.
* New `LavaFrameCompositor`: the manifest is compiled once into typed-data blit plans and every
  diff frame is assembled 1:1 with one `drawRawAtlas` call per source image, then scaled as a
  single image. No per-frame parsing or allocation, no seams or atlas bleeding whatever the
  packing, and composed frames are cached so a looping icon stops compositing after its first
  pass. The cache is all or nothing: a loop that fits the 40 MiB budget is kept whole, one that
  does not keeps only the frame on screen (a partial cache of a loop played in order misses on
  every frame and only costs memory). The compositor lives in the `LavaBundle`, so every widget
  showing the same bundle shares it.
* `LavaBundle.retain` / `release`: widgets count themselves as users of a bundle. When the last
  one leaves, its composed frames are freed, and a large-preview (`_hd`) bundle is also evicted
  from the decode cache and disposed; `LavaIcon` loads it again if it comes back.
* `LavaBundle.openLavaAsset` caches decoded bundles per asset path (`evictOpenLavaCache` releases
  them): a category bar and a preview showing the same icon decode it once.
* Fixed: dragging an interactive icon paused playback for good (`LavaInteractive` now resumes it
  when the drag ends or is cancelled).
* Fixed: `LavaController.configure` did not notify listeners, leaving timelines on stale bounds.
* Fixed: `LavaIcon` could show the bundle of a previously selected demo type when loads finished
  out of order, leaked bundles decoded by `LavaIcon.asset`, and swallowed load errors (they are
  now reported through `FlutterError.reportError`). With an external controller,
  `autoPlay: true` starts it once the bundle is ready.
* Bundles may reference AVIF and WebP images, with an optional `fallbackUrl` per image
  (`LavaManifest.imageFallbacks`). On the web the AVIF is loaded first; because Flutter web's
  `ImageDecoder` rejects every still AVIF on Chrome (flutter/flutter#160600) it is decoded through
  `createImageBitmap` instead. Native platforms load the fallback directly
  (`LavaBundle.preferFallbackImages`): Android 12-15 decode AVIF without its alpha channel and
  without throwing. Load errors are kept apart from decode errors, decoded widths are validated
  against the manifest, and `LavaBundle.undecodableExtensions` reports what fell back.
* Large-preview bundles: `LavaBundle.demoHdAssetPaths` holds every demo icon rendered at 360x324
  (`"density": 4`). `LavaIcon.demo` picks it on its own when it is painted more than 1.35x above
  the standard 180 px (in device pixels), shows the standard bundle first and swaps the large one
  in when its atlas is decoded, keeping the playhead; it never switches back, so resizing a window
  around the threshold does not reload the icon.
* Inspection hooks: `LavaFrameCompositor.blits(frame)` lists the tile blocks a frame is built
  from (source image, source rect, destination rect), `LavaBundle.imageFiles` names the files that
  were actually decoded, `LavaIcon.foregroundPainter` paints inside the icon's tilt / bounce
  transform and `LavaIcon.onBundleChanged` reports the bundle on screen.
* Decoder blame is evidence-based: an extension is only remembered as undecodable when the bytes
  really carry that container's signature (an SPA host answers a missing asset with 200 +
  index.html), a width mismatch falls back without blaming anything, a missing fallback file
  falls back to the primary, and `LavaManifest` equality covers the OpenLava fields.
* `tool/openlava_encode.py` deduplicates tiles across frames (OpenLava `Docs/packing.md`) and
  writes AVIF with a WebP fallback: the seven demo bundles went from 3.1 MB to 1.3 MB (AVIF) /
  1.5 MB (WebP), with smaller decoded atlases.
* Fixed: `LavaManifest.copyWith` dropped the OpenLava fields; `LavaBundle.fromAsset` /
  `fromMemory` leaked the codec when decoding failed.
* New `LavaDemoType.f1Car`: a Formula 1 car from the TV chase camera. Its DRS flap opens
  (squashed against its pivot, with the livery showing through the gap) and closes, titanium
  sparks fly from under the diffuser while it is open, the rain light blinks. Built for tile
  reuse (two body states, four flap positions, two lamp states): 429 atlas tiles instead of
  1230 and a 117 KB bundle, against 430 KB for the same frames as a GIF.
* New `LavaDemoType.f1Front`: the car head-on with the driver's helmet in the cockpit; only the
  front wheels move. They are steered with light alone - the tread highlight slides towards the
  steer and the far side darkens while the outline stays put - so nothing tears against the
  bodywork that covers the tyres. Five distinct frames in a 72-frame loop.
* New `LavaDemoType.sennaMp4`: a 1988-style car on its victory lap with the driver holding the
  Brazilian flag. The still only has a bare pole; the flag is a simulated cloth mesh (travelling
  wave pinned at the hoist, a faster ripple, droop, foreshortening, folds shaded by slope) drawn
  under the car layer, so it loops perfectly and needed no second image.
* New campfire, Christmas tree and helmet bundles: the flame and the fairy lights really relight
  the icon (lit / unlit light pass), the helmet is rendered in 3D and turns on its own axis.
* `tool/` ships the Python pipeline used to key, animate, relight, render and encode new OpenLava
  bundles (`animate_icon.py`, `relight_icon.py`, `lava_sdf.py` + `sdf_scenes.py`,
  `openlava_encode.py`).

## 0.1.0

* Initial release of `lava_flutter`.
* Tile-based frame blitting engine with subpixel coordinate mapping (`TileMath`).
* Native 32-bit alpha channel transparency support.
* Ticker-driven `LavaController` with play, pause, stop, scrubbing, and variable speed.
* Interactive 3D perspective tilt (`Matrix4`) and spring-physics touch bounce.
* Zero-allocation `LavaPainter` using pre-cached paint pipelines.
* Built-in procedural 3D demo icon generator (`LavaDemoBaker`).
