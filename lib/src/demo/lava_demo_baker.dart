import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/painting.dart';

import '../model/lava_manifest.dart';
import '../model/lava_types.dart';

/// Procedural rasterizer that generates 24-frame 3D dimensional
/// micro-animation atlases (Macintosh Cyberdeck and Nature Tree) with 32-bit alpha channel
/// entirely in memory.
abstract final class LavaDemoBaker {
  static ui.Image? _cachedMacImage;
  static ui.Image? _cachedTreeImage;

  /// Default manifest configuration corresponding to the baked atlas.
  static const LavaManifest defaultManifest = LavaManifest(
    version: 1,
    frameRate: 30,
    tileWidth: 128,
    tileHeight: 128,
    columns: 6,
    rows: 4,
    totalFrames: 24,
    loop: true,
  );

  /// Bakes the 24-frame 3D texture atlas for the requested [type].
  ///
  /// Subsequent calls return the cached [ui.Image] instance unless [forceRegenerate]
  /// is set to true.
  static Future<ui.Image> bakeAtlas({
    LavaDemoType type = LavaDemoType.macintosh,
    int tileWidth = 128,
    int tileHeight = 128,
    int columns = 6,
    int rows = 4,
    int totalFrames = 24,
    bool forceRegenerate = false,
  }) async {
    final cached = switch (type) {
      LavaDemoType.macintosh => _cachedMacImage,
      LavaDemoType.sunflower => _cachedTreeImage,
      _ => _cachedMacImage,
    };

    if (cached != null && !forceRegenerate) {
      return cached;
    }

    final totalWidth = columns * tileWidth;
    final totalHeight = rows * tileHeight;

    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);

    for (int i = 0; i < totalFrames; i++) {
      final col = i % columns;
      final row = i ~/ columns;
      final xOffset = (col * tileWidth).toDouble();
      final yOffset = (row * tileHeight).toDouble();

      canvas.save();
      canvas.translate(xOffset, yOffset);
      switch (type) {
        case LavaDemoType.macintosh:
          _renderFrame(
            canvas: canvas,
            frameIndex: i,
            totalFrames: totalFrames,
            width: tileWidth.toDouble(),
            height: tileHeight.toDouble(),
          );
        case LavaDemoType.sunflower:
          _renderTreeFrame(
            canvas: canvas,
            frameIndex: i,
            totalFrames: totalFrames,
            width: tileWidth.toDouble(),
            height: tileHeight.toDouble(),
          );
        default:
          _renderFrame(
            canvas: canvas,
            frameIndex: i,
            totalFrames: totalFrames,
            width: tileWidth.toDouble(),
            height: tileHeight.toDouble(),
          );
      }
      canvas.restore();
    }

    final picture = recorder.endRecording();
    final image = await picture.toImage(totalWidth, totalHeight);
    picture.dispose();

    switch (type) {
      case LavaDemoType.macintosh:
        _cachedMacImage = image;
      case LavaDemoType.sunflower:
        _cachedTreeImage = image;
      default:
        break;
    }
    return image;
  }

  /// Convenience shortcut to bake the 3D nature tree atlas.
  static Future<ui.Image> bakeTreeAtlas({
    int tileWidth = 128,
    int tileHeight = 128,
    int columns = 6,
    int rows = 4,
    int totalFrames = 24,
    bool forceRegenerate = false,
  }) => bakeAtlas(
    type: LavaDemoType.sunflower,
    tileWidth: tileWidth,
    tileHeight: tileHeight,
    columns: columns,
    rows: rows,
    totalFrames: totalFrames,
    forceRegenerate: forceRegenerate,
  );

  /// Clears the cached texture atlases to free GPU memory.
  static void clearCache() {
    _cachedMacImage?.dispose();
    _cachedMacImage = null;
    _cachedTreeImage?.dispose();
    _cachedTreeImage = null;
  }

  static void _renderFrame({
    required Canvas canvas,
    required int frameIndex,
    required int totalFrames,
    required double width,
    required double height,
  }) {
    final t = frameIndex / totalFrames;
    final cx = width / 2.0;
    final cy = height / 2.0;

    // Turntable rotation and isometric pitch (~18 degrees pitch downward)
    final rotY = t * 2 * math.pi;
    const pitch = -0.32;

    // Ambient Occlusion Ground Drop Shadow directly under the chassis base
    final shadowWidth = 50.0 + math.cos(rotY * 2).abs() * 5.0;
    final shadowHeight = 14.0 + math.sin(rotY * 2).abs() * 2.0;

    final shadowPaint =
        Paint()
          ..color = const Color.from(
            alpha: 0.28,
            red: 0.05,
            green: 0.08,
            blue: 0.16,
          )
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6.0);

    final shadowRect = Rect.fromCenter(
      center: Offset(cx, cy + 26.0),
      width: shadowWidth,
      height: shadowHeight,
    );
    canvas.drawOval(shadowRect, shadowPaint);

    // Directional Key Light vector pointing towards light source (Top-Left-Front)
    final lightDir = const _Vec3(-0.4, -0.6, 0.7).normalized();

    // 3D Model Definition: Classic Macintosh 128K
    final faces = _buildMacintoshFaces();

    // Determine if the front chassis is visible to the camera
    const frontNormal = _Vec3(0, 0.05, 1.0);
    final isFrontFacing = frontNormal.rotateY(rotY).rotateX(pitch).z > 0.001;

    // Visible faces with back-face culling (tn.z > 0.001)
    final visibleFaces = <_RenderFace>[];

    for (final face in faces) {
      // Front bezel, chin, and screen are only evaluated when front faces the camera
      if ((face.type == _FaceType.bezel ||
              face.type == _FaceType.chin ||
              face.type == _FaceType.screen) &&
          !isFrontFacing) {
        continue;
      }

      final tn = face.normal.rotateY(rotY).rotateX(pitch);
      if (tn.z > 0.001) {
        final projected = <Offset>[];
        double totalZ = 0.0;

        for (final v in face.vertices) {
          final r = v.rotateY(rotY).rotateX(pitch);
          projected.add(Offset(cx + r.x, cy + r.y));
          totalZ += r.z;
        }

        final avgZ = totalZ / face.vertices.length;
        final diffuse = (0.36 + 0.64 * tn.dot(lightDir)).clamp(0.20, 1.0);
        final shadedColor = _shadeColor(face.color, diffuse);

        visibleFaces.add(
          _RenderFace(
            type: face.type,
            projected: projected,
            avgZ: avgZ,
            diffuse: diffuse,
            color: shadedColor,
            normal: tn,
          ),
        );
      }
    }

    // Depth sort (Painter's algorithm): furthest faces first, closest faces last on top
    visibleFaces.sort((a, b) => a.avgZ.compareTo(b.avgZ));

    final facePaint = Paint()..style = PaintingStyle.fill;
    final edgePaint =
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.9;

    for (final rf in visibleFaces) {
      final path = Path()..moveTo(rf.projected[0].dx, rf.projected[0].dy);
      for (int k = 1; k < rf.projected.length; k++) {
        path.lineTo(rf.projected[k].dx, rf.projected[k].dy);
      }
      path.close();

      // Render base face geometry
      facePaint.color = rf.color;
      canvas.drawPath(path, facePaint);

      // Specular edge highlight
      final rimFactor = (rf.diffuse * 0.40).clamp(0.10, 0.50);
      edgePaint.color = Color.from(
        alpha: rimFactor,
        red: 1.0,
        green: 1.0,
        blue: 1.0,
      );
      canvas.drawPath(path, edgePaint);

      // Decorative face features
      switch (rf.type) {
        case _FaceType.screen:
          _drawCrtContent(canvas, rf.projected, path, t);
        case _FaceType.chin:
          _drawChinDetails(canvas, cx, cy, rotY, pitch);
        case _FaceType.back:
          _drawBackVentilation(canvas, rf.projected);
        case _FaceType.top:
          _drawTopHandle(canvas, rf.projected);
        default:
          break;
      }
    }
  }

  static List<_Face> _buildMacintoshFaces() {
    // Coordinate dimensions
    // Height: top = -22.0, bottom = 22.0
    // Width: bottom = ±18.0, top = ±16.5 (tapered)
    // Depth: back = -14.0, front bottom = 14.0, front top = 11.5 (wedge tilt)
    const vBackBotLeft = _Vec3(-18.0, 22.0, -14.0);
    const vBackBotRight = _Vec3(18.0, 22.0, -14.0);
    const vBackTopRight = _Vec3(16.5, -22.0, -14.0);
    const vBackTopLeft = _Vec3(-16.5, -22.0, -14.0);

    const vFrontBotLeft = _Vec3(-18.0, 22.0, 14.0);
    const vFrontBotRight = _Vec3(18.0, 22.0, 14.0);
    const vFrontTopRight = _Vec3(16.5, -22.0, 11.5);
    const vFrontTopLeft = _Vec3(-16.5, -22.0, 11.5);

    // Front Brow & Chin transition points
    const vBrowBotLeft = _Vec3(-16.5, -15.0, 12.0);
    const vBrowBotRight = _Vec3(16.5, -15.0, 12.0);

    const vChinTopLeft = _Vec3(-17.5, 6.5, 13.5);
    const vChinTopRight = _Vec3(17.5, 6.5, 13.5);

    // Recessed Screen corners
    const vScreenTopLeft = _Vec3(-12.0, -14.0, 11.0);
    const vScreenTopRight = _Vec3(12.0, -14.0, 11.0);
    const vScreenBotRight = _Vec3(12.0, 5.5, 12.5);
    const vScreenBotLeft = _Vec3(-12.0, 5.5, 12.5);

    // Colors (Apple Vintage Platinum / Warm Beige)
    const cTop = Color(0xFFECE6DA);
    const cBottom = Color(0xFFA8A193);
    const cBack = Color(0xFFC7BFA8);
    const cLeft = Color(0xFFBFB7A6);
    const cRight = Color(0xFFD6CEC0);
    const cBezel = Color(0xFFDDD6C7);
    const cScreenBg = Color(0xFF041810);

    return const [
      // 1. Bottom shell
      _Face(
        [vBackBotLeft, vBackBotRight, vFrontBotRight, vFrontBotLeft],
        _Vec3(0, 1, 0),
        cBottom,
        _FaceType.bottom,
      ),
      // 2. Top shell
      _Face(
        [vBackTopLeft, vFrontTopLeft, vFrontTopRight, vBackTopRight],
        _Vec3(0, -1, 0),
        cTop,
        _FaceType.top,
      ),
      // 3. Back shell
      _Face(
        [vBackBotRight, vBackBotLeft, vBackTopLeft, vBackTopRight],
        _Vec3(0, 0, -1),
        cBack,
        _FaceType.back,
      ),
      // 4. Left shell
      _Face(
        [vFrontBotLeft, vBackBotLeft, vBackTopLeft, vFrontTopLeft],
        _Vec3(-1, 0, 0),
        cLeft,
        _FaceType.left,
      ),
      // 5. Right shell
      _Face(
        [vBackBotRight, vFrontBotRight, vFrontTopRight, vBackTopRight],
        _Vec3(1, 0, 0),
        cRight,
        _FaceType.right,
      ),
      // 6. Front Brow (above CRT screen)
      _Face(
        [vBrowBotLeft, vBrowBotRight, vFrontTopRight, vFrontTopLeft],
        _Vec3(0, 0.05, 1.0),
        cBezel,
        _FaceType.bezel,
      ),
      // 7. Front Chin (below CRT screen, holding floppy drive)
      _Face(
        [vFrontBotLeft, vFrontBotRight, vChinTopRight, vChinTopLeft],
        _Vec3(0, 0.05, 1.0),
        cBezel,
        _FaceType.chin,
      ),
      // 8. Left Bezel Cheek
      _Face(
        [
          vChinTopLeft,
          _Vec3(-12.0, 6.5, 13.5),
          _Vec3(-12.0, -15.0, 12.0),
          vBrowBotLeft,
        ],
        _Vec3(0, 0.05, 1.0),
        cBezel,
        _FaceType.bezel,
      ),
      // 9. Right Bezel Cheek
      _Face(
        [
          _Vec3(12.0, 6.5, 13.5),
          vChinTopRight,
          vBrowBotRight,
          _Vec3(12.0, -15.0, 12.0),
        ],
        _Vec3(0, 0.05, 1.0),
        cBezel,
        _FaceType.bezel,
      ),
      // 10. Phosphor CRT Screen Face
      _Face(
        [vScreenBotLeft, vScreenBotRight, vScreenTopRight, vScreenTopLeft],
        _Vec3(0, 0.05, 1.0),
        cScreenBg,
        _FaceType.screen,
      ),
    ];
  }

  static void _drawCrtContent(
    Canvas canvas,
    List<Offset> pts,
    Path screenPath,
    double t,
  ) {
    canvas.save();
    canvas.clipPath(screenPath);

    // Deep glowing CRT background
    final crtBounds = screenPath.getBounds();
    final crtBgPaint =
        Paint()
          ..shader = ui.Gradient.linear(
            crtBounds.topLeft,
            crtBounds.bottomRight,
            const [Color(0xFF031A12), Color(0xFF052B1E), Color(0xFF02120C)],
            const [0.0, 0.5, 1.0],
          );
    canvas.drawRect(crtBounds, crtBgPaint);

    // Inner bezel shadow giving recessed depth
    final innerShadowPaint =
        Paint()
          ..color = const Color(0x77000000)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5;
    canvas.drawRect(crtBounds.deflate(0.75), innerShadowPaint);

    // CRT Scanlines
    final scanlinePaint =
        Paint()
          ..color = const Color.from(
            alpha: 0.18,
            red: 0.0,
            green: 0.0,
            blue: 0.0,
          )
          ..strokeWidth = 1.0;
    for (double y = crtBounds.top; y <= crtBounds.bottom; y += 2.0) {
      canvas.drawLine(
        Offset(crtBounds.left, y),
        Offset(crtBounds.right, y),
        scanlinePaint,
      );
    }

    // Glowing Phosphor Terminal Prompt
    final phosphorPaint =
        Paint()
          ..color = const Color(0xFF00FF9D)
          ..style = PaintingStyle.fill;

    // Terminal command text bar & cursor
    final textX = crtBounds.left + crtBounds.width * 0.16;
    final textY1 = crtBounds.top + crtBounds.height * 0.28;
    final textY2 = crtBounds.top + crtBounds.height * 0.50;

    // Line 1: Code block / title bar
    canvas.drawRect(
      Rect.fromLTWH(textX, textY1, crtBounds.width * 0.55, 2.0),
      phosphorPaint,
    );

    // Line 2: Retro terminal prompt `>_`
    final promptPath =
        Path()
          ..moveTo(textX, textY2)
          ..lineTo(textX + 3.0, textY2 + 2.0)
          ..lineTo(textX, textY2 + 4.0);
    final promptStroke =
        Paint()
          ..color = const Color(0xFF00FF9D)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.2;
    canvas.drawPath(promptPath, promptStroke);

    // Blinking cursor
    final cursorVisible = (t * 6).floor() % 2 == 0;
    if (cursorVisible) {
      final cursorPaint = Paint()..color = const Color(0xFF50FFAF);
      canvas.drawRect(
        Rect.fromLTWH(textX + 6.0, textY2, 3.5, 4.5),
        cursorPaint,
      );
    }

    // Phosphor Inner Radial Bloom
    final bloomPaint =
        Paint()
          ..color = const Color.from(
            alpha: 0.22,
            red: 0.0,
            green: 1.0,
            blue: 0.6,
          )
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5.0);
    canvas.drawCircle(crtBounds.center, crtBounds.width * 0.32, bloomPaint);

    // Specular curved CRT glass reflection streak
    final glarePaint =
        Paint()
          ..shader = ui.Gradient.linear(crtBounds.topLeft, crtBounds.center, [
            const Color.from(alpha: 0.45, red: 1.0, green: 1.0, blue: 1.0),
            const Color.from(alpha: 0.0, red: 1.0, green: 1.0, blue: 1.0),
          ]);
    final glarePath =
        Path()
          ..moveTo(crtBounds.left, crtBounds.top)
          ..lineTo(crtBounds.left + crtBounds.width * 0.65, crtBounds.top)
          ..lineTo(crtBounds.left, crtBounds.top + crtBounds.height * 0.65)
          ..close();
    canvas.drawPath(glarePath, glarePaint);

    canvas.restore();
  }

  static void _drawChinDetails(
    Canvas canvas,
    double cx,
    double cy,
    double rotY,
    double pitch,
  ) {
    // 3D Floppy Drive Slot
    final slotP1 = const _Vec3(-7.5, 13.0, 13.8).rotateY(rotY).rotateX(pitch);
    final slotP2 = const _Vec3(7.5, 13.0, 13.8).rotateY(rotY).rotateX(pitch);
    final slotP3 = const _Vec3(7.5, 14.8, 13.8).rotateY(rotY).rotateX(pitch);
    final slotP4 = const _Vec3(-7.5, 14.8, 13.8).rotateY(rotY).rotateX(pitch);

    final slotPath =
        Path()
          ..moveTo(cx + slotP1.x, cy + slotP1.y)
          ..lineTo(cx + slotP2.x, cy + slotP2.y)
          ..lineTo(cx + slotP3.x, cy + slotP3.y)
          ..lineTo(cx + slotP4.x, cy + slotP4.y)
          ..close();

    final slotPaint = Paint()..color = const Color(0xFF262420);
    canvas.drawPath(slotPath, slotPaint);

    // Drive read activity LED (emerald green dot)
    final ledPt = const _Vec3(9.2, 13.9, 13.8).rotateY(rotY).rotateX(pitch);
    final ledPaint =
        Paint()
          ..color = const Color(0xFF00FF66)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 1.2);
    canvas.drawCircle(Offset(cx + ledPt.x, cy + ledPt.y), 1.2, ledPaint);

    // Retro Rainbow Badge (6 iconic stripes)
    const rainbowColors = [
      Color(0xFF61BB46), // Green
      Color(0xFFFDB827), // Yellow
      Color(0xFFF58220), // Orange
      Color(0xFFE03A3E), // Red
      Color(0xFF963D97), // Purple
      Color(0xFF009DDC), // Blue
    ];

    for (int s = 0; s < rainbowColors.length; s++) {
      final y0 = 12.5 + (s * 0.5);
      final y1 = y0 + 0.45;
      final b1 = _Vec3(-14.2, y0, 13.8).rotateY(rotY).rotateX(pitch);
      final b2 = _Vec3(-12.2, y0, 13.8).rotateY(rotY).rotateX(pitch);
      final b3 = _Vec3(-12.2, y1, 13.8).rotateY(rotY).rotateX(pitch);
      final b4 = _Vec3(-14.2, y1, 13.8).rotateY(rotY).rotateX(pitch);

      final badgePath =
          Path()
            ..moveTo(cx + b1.x, cy + b1.y)
            ..lineTo(cx + b2.x, cy + b2.y)
            ..lineTo(cx + b3.x, cy + b3.y)
            ..lineTo(cx + b4.x, cy + b4.y)
            ..close();

      canvas.drawPath(badgePath, Paint()..color = rainbowColors[s]);
    }
  }

  static void _drawBackVentilation(Canvas canvas, List<Offset> pts) {
    if (pts.length < 4) return;
    // Horizontal ventilation grille lines
    // Face vertices: [vBackBotRight, vBackBotLeft, vBackTopLeft, vBackTopRight]
    final pBotRight = pts[0];
    final pBotLeft = pts[1];
    final pTopLeft = pts[2];
    final pTopRight = pts[3];

    final ventPaint =
        Paint()
          ..color = const Color(0xFF5E574B)
          ..strokeWidth = 1.0;

    for (int i = 2; i <= 6; i++) {
      final frac = i / 10.0;
      final start = Offset.lerp(pTopLeft, pBotLeft, frac)!;
      final end = Offset.lerp(pTopRight, pBotRight, frac)!;
      final leftInset = Offset.lerp(start, end, 0.22)!;
      final rightInset = Offset.lerp(start, end, 0.78)!;
      canvas.drawLine(leftInset, rightInset, ventPaint);
    }

    // Lower ports panel
    final portStart = Offset.lerp(pTopLeft, pBotLeft, 0.75)!;
    final portEnd = Offset.lerp(pTopRight, pBotRight, 0.75)!;
    final portBotStart = Offset.lerp(pTopLeft, pBotLeft, 0.90)!;
    final portBotEnd = Offset.lerp(pTopRight, pBotRight, 0.90)!;

    final portPath =
        Path()
          ..moveTo(
            Offset.lerp(portStart, portEnd, 0.20)!.dx,
            Offset.lerp(portStart, portEnd, 0.20)!.dy,
          )
          ..lineTo(
            Offset.lerp(portStart, portEnd, 0.80)!.dx,
            Offset.lerp(portStart, portEnd, 0.80)!.dy,
          )
          ..lineTo(
            Offset.lerp(portBotStart, portBotEnd, 0.80)!.dx,
            Offset.lerp(portBotStart, portBotEnd, 0.80)!.dy,
          )
          ..lineTo(
            Offset.lerp(portBotStart, portBotEnd, 0.20)!.dx,
            Offset.lerp(portBotStart, portBotEnd, 0.20)!.dy,
          )
          ..close();

    canvas.drawPath(portPath, Paint()..color = const Color(0xFF4A443A));
  }

  static void _drawTopHandle(Canvas canvas, List<Offset> pts) {
    if (pts.length < 4) return;
    // Recessed carrying handle cavity
    final handleCenter = (pts[0] + pts[1] + pts[2] + pts[3]) / 4.0;
    final handlePaint =
        Paint()
          ..color = const Color(0xFF918A7C)
          ..style = PaintingStyle.fill;

    final handleRect = Rect.fromCenter(
      center: handleCenter,
      width: 14.0,
      height: 4.5,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(handleRect, const Radius.circular(2.0)),
      handlePaint,
    );
  }

  static void _renderTreeFrame({
    required Canvas canvas,
    required int frameIndex,
    required int totalFrames,
    required double width,
    required double height,
  }) {
    final t = frameIndex / totalFrames;
    final cx = width / 2.0;
    final cy = height / 2.0;

    // Full 360-degree turntable rotation around Y-axis
    final rotY = t * 2 * math.pi;
    const pitch = -0.28;

    // Dynamic wind sway (primary harmonic sway + secondary flutter)
    final wind = math.sin(t * 2 * math.pi) * 0.12;
    final windOffset = math.sin(t * 2 * math.pi) * 8.0;
    final windCanopy = math.sin(t * 2 * math.pi - 0.4) * 12.0;

    // 1. Soft Ground Ambient Occlusion Shadow
    final shadowWidth = 54.0 + math.cos(rotY * 2).abs() * 6.0;
    final shadowHeight = 16.0 + math.sin(rotY * 2).abs() * 3.0;
    final shadowPaint =
        Paint()
          ..color = const Color.from(
            alpha: 0.32,
            red: 0.05,
            green: 0.10,
            blue: 0.06,
          )
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7.0);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(cx, cy + 34.0),
        width: shadowWidth,
        height: shadowHeight,
      ),
      shadowPaint,
    );

    // 2. 3D Floating Hexagonal Island Base (Earth strata & lush grass cap)
    _drawTreeGroundBase(canvas, cx, cy, rotY, pitch, wind);

    // 3. 3D Trunk, Root Buttresses, and Branches (with front/back depth sorting)
    _drawTreeTrunkAndBranches(
      canvas,
      cx,
      cy,
      rotY,
      pitch,
      windOffset,
      windCanopy,
      t,
    );

    // 4. Volumetric Foliage Canopy (5 Asymmetrical Clusters with 3D Key Lighting)
    _drawTreeCanopy(canvas, cx, cy, rotY, pitch, windCanopy, t);

    // 5. Ruby Apples with 3D Depth
    _drawTreeFruits(canvas, cx, cy, rotY, pitch, windCanopy);

    // 6. Fluttering Golden Leaves Orbiting in 3D
    _drawFlutteringLeaves(canvas, cx, cy, rotY, pitch, t);
  }

  static void _drawTreeGroundBase(
    Canvas canvas,
    double cx,
    double cy,
    double rotY,
    double pitch,
    double wind,
  ) {
    const segments = 6;
    const topRadius = 26.0;
    const botRadius = 17.0;
    const topY = 22.0;
    const botY = 30.0;

    final topPts = <Offset>[];
    final botPts = <Offset>[];

    for (int k = 0; k < segments; k++) {
      final angle = (k * 2 * math.pi) / segments;
      final topV = _Vec3(
        math.cos(angle) * topRadius,
        topY,
        math.sin(angle) * topRadius,
      ).rotateY(rotY).rotateX(pitch);
      final botV = _Vec3(
        math.cos(angle) * botRadius,
        botY,
        math.sin(angle) * botRadius,
      ).rotateY(rotY).rotateX(pitch);

      topPts.add(Offset(cx + topV.x, cy + topV.y));
      botPts.add(Offset(cx + botV.x, cy + botV.y));
    }

    // Draw earthen strata side quads facing the camera
    for (int k = 0; k < segments; k++) {
      final nextK = (k + 1) % segments;
      final angleMid = ((k + 0.5) * 2 * math.pi) / segments;
      final faceNorm = _Vec3(
        math.cos(angleMid),
        0.3,
        math.sin(angleMid),
      ).rotateY(rotY).rotateX(pitch);

      if (faceNorm.z > 0.0) {
        final quad =
            Path()
              ..moveTo(topPts[k].dx, topPts[k].dy)
              ..lineTo(topPts[nextK].dx, topPts[nextK].dy)
              ..lineTo(botPts[nextK].dx, botPts[nextK].dy)
              ..lineTo(botPts[k].dx, botPts[k].dy)
              ..close();

        final diff = (0.55 + faceNorm.z * 0.45).clamp(0.4, 1.0);
        final dirtColor =
            Color.lerp(const Color(0xFF3E2723), const Color(0xFF795548), diff)!;

        canvas.drawPath(quad, Paint()..color = dirtColor);
      }
    }

    // Top lush grass hexagonal lawn cap
    final grassPath = Path()..moveTo(topPts[0].dx, topPts[0].dy);
    for (int k = 1; k < segments; k++) {
      grassPath.lineTo(topPts[k].dx, topPts[k].dy);
    }
    grassPath.close();

    final grassPaint =
        Paint()
          ..shader = ui.Gradient.linear(
            Offset(cx - 20, cy + 18),
            Offset(cx + 20, cy + 26),
            const [Color(0xFF81C784), Color(0xFF43A047), Color(0xFF2E7D32)],
            const [0.0, 0.5, 1.0],
          );
    canvas.drawPath(grassPath, grassPaint);

    // Grassy edge rim highlight
    canvas.drawPath(
      grassPath,
      Paint()
        ..color = const Color(0x66A5D6A7)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0,
    );
  }

  static void _drawTreeTrunkAndBranches(
    Canvas canvas,
    double cx,
    double cy,
    double rotY,
    double pitch,
    double windOffset,
    double windCanopy,
    double t,
  ) {
    // 3D Trunk Centerline
    final trunkBot = const _Vec3(0, 22.0, 0);
    final trunkMid = _Vec3(windOffset * 0.4, 9.0, 0);
    final trunkFork = _Vec3(windOffset * 0.8, -4.0, 0);

    final b1 = trunkBot.rotateY(rotY).rotateX(pitch);
    final b2 = trunkMid.rotateY(rotY).rotateX(pitch);
    final b3 = trunkFork.rotateY(rotY).rotateX(pitch);

    // 4 Extended 3D Branches with distinct 3D azimuths
    final branches = [
      // Branch A: Front-Right (+X, +Z)
      (
        tip: _Vec3(18.0 + windCanopy, -8.0, 14.0).rotateY(rotY).rotateX(pitch),
        width: 3.2,
        isFront: true,
      ),
      // Branch B: Left Reach (-X, +Z)
      (
        tip: _Vec3(-20.0 + windCanopy, -4.0, 2.0).rotateY(rotY).rotateX(pitch),
        width: 3.0,
        isFront: true,
      ),
      // Branch C: Back-Right (+X, -Z)
      (
        tip: _Vec3(
          14.0 + windCanopy,
          -10.0,
          -16.0,
        ).rotateY(rotY).rotateX(pitch),
        width: 2.6,
        isFront: false,
      ),
      // Branch D: High Crown Fork (-X, -Z)
      (
        tip: _Vec3(-2.0 + windCanopy, -18.0, -4.0).rotateY(rotY).rotateX(pitch),
        width: 2.8,
        isFront: false,
      ),
    ];

    final branchPaint =
        Paint()
          ..color = const Color(0xFF5D4037)
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round;

    // Draw Back Branches first (Z < 0)
    for (final b in branches) {
      if (b.tip.z < b3.z) {
        branchPaint.strokeWidth = b.width;
        canvas.drawLine(
          Offset(cx + b3.x, cy + b3.y),
          Offset(cx + b.tip.x, cy + b.tip.y),
          branchPaint,
        );
      }
    }

    // Draw Main Trunk Segment with dynamic bark lighting
    final trunkPath =
        Path()
          ..moveTo(cx + b1.x - 5.0, cy + b1.y)
          ..lineTo(cx + b2.x - 3.8, cy + b2.y)
          ..lineTo(cx + b3.x - 3.0, cy + b3.y)
          ..lineTo(cx + b3.x + 3.0, cy + b3.y)
          ..lineTo(cx + b2.x + 3.8, cy + b2.y)
          ..lineTo(cx + b1.x + 5.0, cy + b1.y)
          ..close();

    // Shifting bark highlight based on rotation
    final lightShift = math.cos(rotY) * 3.5;
    final trunkPaint =
        Paint()
          ..shader = ui.Gradient.linear(
            Offset(cx + b2.x - 5.0 + lightShift, cy + b2.y),
            Offset(cx + b2.x + 5.0 + lightShift, cy + b2.y),
            const [Color(0xFF8D6E63), Color(0xFF5D4037), Color(0xFF3E2723)],
            const [0.0, 0.5, 1.0],
          );
    canvas.drawPath(trunkPath, trunkPaint);

    // Front/Back Distinct 3D Landmarks:
    // Front: Moss patch when facing viewer (cos(rotY) > 0.2)
    final facingFront = math.cos(rotY);
    if (facingFront > 0.2) {
      final mossPaint =
          Paint()
            ..color = const Color(0x9981C784)
            ..style = PaintingStyle.fill;
      canvas.drawCircle(
        Offset(cx + b2.x - 1.2, cy + b2.y + 2.0),
        2.2,
        mossPaint,
      );
    }
    // Back: Owl hollow tree knot when facing away (cos(rotY) < -0.2)
    if (facingFront < -0.2) {
      final hollowPaint = Paint()..color = const Color(0xFF271A14);
      final knotPos = Offset(cx + b2.x, cy + b2.y + 1.0);
      canvas.drawOval(
        Rect.fromCenter(center: knotPos, width: 3.4, height: 4.8),
        hollowPaint,
      );
      // Glowing amber eyes inside knot
      final eyePaint = Paint()..color = const Color(0xFFFFD54F);
      canvas.drawCircle(knotPos + const Offset(-0.8, -0.6), 0.5, eyePaint);
      canvas.drawCircle(knotPos + const Offset(0.8, -0.6), 0.5, eyePaint);
    }

    // Draw Front Branches (Z >= 0)
    for (final b in branches) {
      if (b.tip.z >= b3.z) {
        branchPaint.strokeWidth = b.width;
        canvas.drawLine(
          Offset(cx + b3.x, cy + b3.y),
          Offset(cx + b.tip.x, cy + b.tip.y),
          branchPaint,
        );
      }
    }

    // 3D Hanging Birdhouse on Branch A (tip of Front-Right branch)
    final birdhouseTip = branches[0].tip;
    _drawBirdhouse(canvas, cx, cy, birdhouseTip, t);
  }

  static void _drawBirdhouse(
    Canvas canvas,
    double cx,
    double cy,
    _Vec3 branchTip,
    double t,
  ) {
    final tipPos = Offset(cx + branchTip.x, cy + branchTip.y);
    final swing = math.sin(t * 4 * math.pi) * 2.0;

    // Hanging cord
    final houseCenter = tipPos + Offset(swing, 13.0);
    final cordPaint =
        Paint()
          ..color = const Color(0xFFD7CCC8)
          ..strokeWidth = 0.9;
    canvas.drawLine(tipPos, houseCenter + const Offset(0, -5.0), cordPaint);

    // Only draw detailed birdhouse if in front of back-plane
    if (branchTip.z > -10.0) {
      // House body
      final bodyRect = Rect.fromCenter(
        center: houseCenter,
        width: 8.0,
        height: 8.5,
      );
      canvas.drawRRect(
        RRect.fromRectAndRadius(bodyRect, const Radius.circular(1.5)),
        Paint()..color = const Color(0xFFBCAAA4),
      );

      // Red pitched roof
      final roofPath =
          Path()
            ..moveTo(houseCenter.dx, houseCenter.dy - 7.5)
            ..lineTo(houseCenter.dx + 5.5, houseCenter.dy - 3.5)
            ..lineTo(houseCenter.dx - 5.5, houseCenter.dy - 3.5)
            ..close();
      canvas.drawPath(roofPath, Paint()..color = const Color(0xFFE53935));

      // Circular entry hole
      canvas.drawCircle(
        houseCenter + const Offset(0, -0.5),
        1.4,
        Paint()..color = const Color(0xFF3E2723),
      );

      // Perch peg
      canvas.drawLine(
        houseCenter + const Offset(0, 1.8),
        houseCenter + const Offset(0, 3.2),
        Paint()
          ..color = const Color(0xFF8D6E63)
          ..strokeWidth = 1.0,
      );
    }
  }

  static void _drawTreeCanopy(
    Canvas canvas,
    double cx,
    double cy,
    double rotY,
    double pitch,
    double windCanopy,
    double t,
  ) {
    // 5 Asymmetrical 3D Foliage Clusters
    final clusters = [
      // 1. High Crown
      (
        center: const _Vec3(0.0, -22.0, 0.0),
        radius: 17.5,
        windFactor: 1.0,
        colors: const [Color(0xFFA5D6A7), Color(0xFF66BB6A), Color(0xFF2E7D32)],
      ),
      // 2. Front-Right
      (
        center: const _Vec3(16.0, -10.0, 10.0),
        radius: 15.0,
        windFactor: 0.8,
        colors: const [Color(0xFF81C784), Color(0xFF43A047), Color(0xFF1B5E20)],
      ),
      // 3. Front-Left
      (
        center: const _Vec3(-16.0, -6.0, 12.0),
        radius: 14.5,
        windFactor: 0.7,
        colors: const [Color(0xFFA5D6A7), Color(0xFF4CAF50), Color(0xFF2E7D32)],
      ),
      // 4. Back-Right
      (
        center: const _Vec3(14.0, -14.0, -12.0),
        radius: 13.5,
        windFactor: 0.6,
        colors: const [Color(0xFF66BB6A), Color(0xFF388E3C), Color(0xFF1B5E20)],
      ),
      // 5. Back-Left
      (
        center: const _Vec3(-14.0, -12.0, -12.0),
        radius: 14.0,
        windFactor: 0.7,
        colors: const [Color(0xFF4CAF50), Color(0xFF2E7D32), Color(0xFF0D3813)],
      ),
    ];

    // Project and depth-sort foliage clusters (Painter's Algorithm: lowest Z first)
    final rendered = <_RenderClusterWithColors>[];
    for (final c in clusters) {
      final shifted = _Vec3(
        c.center.x + (windCanopy * c.windFactor),
        c.center.y,
        c.center.z,
      );
      final r = shifted.rotateY(rotY).rotateX(pitch);
      rendered.add(
        _RenderClusterWithColors(
          pos: Offset(cx + r.x, cy + r.y),
          depthZ: r.z,
          radius: c.radius,
          colors: c.colors,
        ),
      );
    }
    rendered.sort((a, b) => a.depthZ.compareTo(b.depthZ));

    for (final rc in rendered) {
      // 3D Spherical Radial Key Lighting
      final lightOffset = rc.pos + Offset(-rc.radius * 0.35, -rc.radius * 0.35);
      final puffPaint =
          Paint()
            ..shader = ui.Gradient.radial(
              lightOffset,
              rc.radius * 1.35,
              rc.colors,
              const [0.0, 0.55, 1.0],
            );
      canvas.drawCircle(rc.pos, rc.radius, puffPaint);

      // Fluffy Studio Ghibli style cloud scalloping around perimeter
      final floretPaint = Paint()..color = rc.colors[1].withValues(alpha: 0.85);
      for (int i = 0; i < 6; i++) {
        final floretAngle = (i * 2 * math.pi / 6.0) + (t * 0.5);
        final floretPos =
            rc.pos +
            Offset(
              math.cos(floretAngle) * (rc.radius * 0.75),
              math.sin(floretAngle) * (rc.radius * 0.75),
            );
        canvas.drawCircle(floretPos, rc.radius * 0.45, floretPaint);
      }

      // Specular rim crescent
      final rimPaint =
          Paint()
            ..color = const Color(0x33FFFFFF)
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.0;
      canvas.drawCircle(rc.pos, rc.radius, rimPaint);
    }
  }

  static void _drawTreeFruits(
    Canvas canvas,
    double cx,
    double cy,
    double rotY,
    double pitch,
    double windCanopy,
  ) {
    const fruits = [
      _Vec3(-10.0, -8.0, 15.0),
      _Vec3(12.0, -4.0, 14.0),
      _Vec3(-2.0, -20.0, 16.0),
      _Vec3(10.0, -12.0, -11.0),
      _Vec3(-12.0, -4.0, -12.0),
      _Vec3(2.0, -21.0, -15.0),
      _Vec3(18.0, -7.0, 6.0),
      _Vec3(-18.0, -3.0, 8.0),
    ];

    final fruitPaint = Paint()..style = PaintingStyle.fill;
    final glintPaint = Paint()..color = const Color(0xEEFFFFFF);
    final stemPaint =
        Paint()
          ..color = const Color(0xFF33691E)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.9;

    for (final f in fruits) {
      final shifted = _Vec3(f.x + (windCanopy * 0.7), f.y, f.z);
      final r = shifted.rotateY(rotY).rotateX(pitch);

      // Only draw fruits facing toward camera (+Z)
      if (r.z > 0.0) {
        final pos = Offset(cx + r.x, cy + r.y);
        const radius = 2.8;

        // Apple body
        fruitPaint.color = const Color(0xFFE53935);
        canvas.drawCircle(pos, radius, fruitPaint);

        // Specular glint
        canvas.drawCircle(pos + const Offset(-0.8, -0.8), 0.8, glintPaint);

        // Stem
        canvas.drawLine(
          pos + const Offset(0, -radius),
          pos + const Offset(0.8, -radius - 1.2),
          stemPaint,
        );
      }
    }
  }

  static void _drawFlutteringLeaves(
    Canvas canvas,
    double cx,
    double cy,
    double rotY,
    double pitch,
    double t,
  ) {
    // 3 Fluttering golden autumn leaves orbiting around the tree
    const leafCount = 3;
    for (int k = 0; k < leafCount; k++) {
      final phase = (k * 2 * math.pi) / leafCount;
      final leafAngle = (t * 2 * math.pi) + phase;
      const leafRadius = 26.0;
      final leafY = -14.0 + math.sin(leafAngle * 2.0) * 8.0;

      final leafVec = _Vec3(
        math.cos(leafAngle) * leafRadius,
        leafY,
        math.sin(leafAngle) * leafRadius,
      ).rotateY(rotY).rotateX(pitch);

      if (leafVec.z > -6.0) {
        final pos = Offset(cx + leafVec.x, cy + leafVec.y);
        final leafTilt = math.sin(t * 6 * math.pi + phase) * 0.45;

        canvas.save();
        canvas.translate(pos.dx, pos.dy);
        canvas.rotate(leafTilt);

        final leafPath =
            Path()
              ..moveTo(0, -3.2)
              ..quadraticBezierTo(2.6, -1.0, 0, 3.2)
              ..quadraticBezierTo(-2.6, -1.0, 0, -3.2)
              ..close();

        final leafPaint =
            Paint()
              ..color = const Color(0xFFFFB300)
              ..style = PaintingStyle.fill;
        canvas.drawPath(leafPath, leafPaint);

        final veinPaint =
            Paint()
              ..color = const Color(0xFFE65100)
              ..style = PaintingStyle.stroke
              ..strokeWidth = 0.6;
        canvas.drawLine(const Offset(0, -2.8), const Offset(0, 2.8), veinPaint);

        canvas.restore();
      }
    }
  }

  static Color _shadeColor(Color base, double factor) {
    return Color.from(
      alpha: base.a,
      red: (base.r * factor).clamp(0.0, 1.0),
      green: (base.g * factor).clamp(0.0, 1.0),
      blue: (base.b * factor).clamp(0.0, 1.0),
    );
  }
}

class _RenderClusterWithColors {
  const _RenderClusterWithColors({
    required this.pos,
    required this.depthZ,
    required this.radius,
    required this.colors,
  });
  final Offset pos;
  final double depthZ;
  final double radius;
  final List<Color> colors;
}

enum _FaceType { body, top, bottom, back, left, right, bezel, chin, screen }

class _Vec3 {
  const _Vec3(this.x, this.y, this.z);
  final double x;
  final double y;
  final double z;

  _Vec3 rotateY(double angle) {
    final cosA = math.cos(angle);
    final sinA = math.sin(angle);
    return _Vec3(x * cosA + z * sinA, y, -x * sinA + z * cosA);
  }

  _Vec3 rotateX(double angle) {
    final cosA = math.cos(angle);
    final sinA = math.sin(angle);
    return _Vec3(x, y * cosA - z * sinA, y * sinA + z * cosA);
  }

  double dot(_Vec3 o) => x * o.x + y * o.y + z * o.z;

  _Vec3 normalized() {
    final len = math.sqrt(x * x + y * y + z * z);
    if (len == 0) return this;
    return _Vec3(x / len, y / len, z / len);
  }
}

class _Face {
  const _Face(
    this.vertices,
    this.normal,
    this.color, [
    this.type = _FaceType.body,
  ]);
  final List<_Vec3> vertices;
  final _Vec3 normal;
  final Color color;
  final _FaceType type;
}

class _RenderFace {
  const _RenderFace({
    required this.type,
    required this.projected,
    required this.avgZ,
    required this.diffuse,
    required this.color,
    required this.normal,
  });

  final _FaceType type;
  final List<Offset> projected;
  final double avgZ;
  final double diffuse;
  final Color color;
  final _Vec3 normal;
}
