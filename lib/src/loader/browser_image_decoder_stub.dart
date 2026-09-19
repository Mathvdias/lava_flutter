import 'dart:typed_data';
import 'dart:ui' as ui;

/// Off the web there is no browser to ask: `null` means "not available here".
Future<ui.Image?> decodeImageInBrowser(
  Uint8List bytes,
  String mimeType,
) async => null;
