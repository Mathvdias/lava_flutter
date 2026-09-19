import 'dart:js_interop';
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'dart:ui_web' as ui_web;

@JS('Blob')
extension type _Blob._(JSObject _) implements JSObject {
  external factory _Blob(JSArray<JSAny> parts, _BlobOptions options);
}

extension type _BlobOptions._(JSObject _) implements JSObject {
  external factory _BlobOptions({String type});
}

extension type _ImageBitmapOptions._(JSObject _) implements JSObject {
  external factory _ImageBitmapOptions({
    String premultiplyAlpha,
    String colorSpaceConversion,
  });
}

@JS('createImageBitmap')
external JSPromise<JSObject> _createImageBitmap(
  _Blob blob,
  _ImageBitmapOptions options,
);

/// Decodes [bytes] with the browser's own image pipeline (`createImageBitmap`)
/// and hands the bitmap to the renderer.
///
/// Flutter web decodes through the WebCodecs `ImageDecoder` with
/// `preferAnimation: true`, and Chrome rejects every *still* AVIF under that
/// option ("Failed to retrieve track metadata") although it decodes the same
/// file everywhere else. Going through `createImageBitmap` sidesteps it.
/// Throws when the browser cannot decode the format either.
Future<ui.Image?> decodeImageInBrowser(Uint8List bytes, String mimeType) async {
  final blob = _Blob([bytes.toJS].toJS, _BlobOptions(type: mimeType));
  final bitmap =
      await _createImageBitmap(
        blob,
        // Same choices the engine makes for its own decodes.
        _ImageBitmapOptions(
          premultiplyAlpha: 'premultiply',
          colorSpaceConversion: 'default',
        ),
      ).toDart;
  return ui_web.createImageFromImageBitmap(bitmap);
}
