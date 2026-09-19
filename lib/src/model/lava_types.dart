/// Represents the current playback status of a Lava animation.
enum LavaPlaybackStatus {
  /// The animation is stopped and positioned at the initial frame.
  stopped,

  /// The animation is actively ticking and playing frames.
  playing,

  /// The animation is paused at the current frame.
  paused,

  /// The non-looping animation reached its final frame.
  completed,
}

/// Represents the interaction state for tactile 3D feedback.
enum LavaInteractiveState {
  /// Default resting state.
  idle,

  /// Pointer is hovering over the icon (3D perspective tilt active).
  hover,

  /// Pointer is actively pressing the icon (spring compression active).
  pressed,
}

/// Built-in demo icon bundles (OpenLava diff tilesets shipped with the host app).
enum LavaDemoType {
  /// Classic 1984 Macintosh 128K rendered in 3D, hovering with a soft contact shadow
  /// (`assets/lava/macintosh`; falls back to the procedural baker when absent).
  macintosh,

  /// 3D sunflower in a terracotta pot: stem bends in the wind, the head turns
  /// and pollen drifts up (`assets/lava/sunflower`; falls back to the procedural
  /// tree baker when absent).
  sunflower,

  /// Retro 1970s Lava Lamp with glowing internal bulb, molten wax blobs, and
  /// brushed aluminum cone base (`assets/lava/lavalamp`).
  lavaLamp,

  /// Campfire in a stone ring: the flame sways and its flickering light
  /// really relights the logs and stones (`assets/lava/campfire`).
  campfire,

  /// Classic 1950s atomic sci-fi retro space rocket with fire thruster plume,
  /// mach diamonds, and incandescent glowing sparks (`assets/lava/rocket`).
  rocket,

  /// Yellow racing helmet with green and blue bands, rendered in real 3D and
  /// turning 360 degrees on its own axis (`assets/lava/senna`, 72 frames @ 24 fps).
  senna,

  /// Snow-dusted Christmas tree whose fairy lights blink one by one, each
  /// casting its own pool of light, under falling snow (`assets/lava/christmastree`).
  christmasTree,

  /// Formula 1 car from the TV chase camera in a navy, red and yellow livery:
  /// the DRS flap opens and closes, titanium sparks fly from under the diffuser
  /// while it is open, and the rain light blinks (`assets/lava/f1car`).
  f1Car,

  /// The same car head-on, the driver's white, red and navy helmet with a gold
  /// lion in the cockpit; only the front wheels move, weaving slightly left and
  /// right - five distinct frames, the smallest bundle of the set
  /// (`assets/lava/f1front`).
  f1Front,

  /// A 1988-style red and white Formula 1 car on its victory lap, the driver in
  /// a yellow helmet holding the Brazilian flag out of the cockpit; the flag is
  /// simulated cloth waving behind the car (`assets/lava/sennamp4`).
  sennaMp4,
}
