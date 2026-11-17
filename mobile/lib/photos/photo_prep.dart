import 'dart:math';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter_image_compress/flutter_image_compress.dart';

import 'jpeg_metadata.dart';

/// 웹(static/js/photo-resize.js)과 같은 기준: 긴 변이 이 값 아래로 내려가지 않는 데까지만 절반씩 줄인다(결과 2000~3999px).
/// 마지막 1600px 축소는 서버(Pillow Lanczos)가 한다.
const resizeMinSide = 2000;

/// 웹과 같은 JPEG 품질(0.9)
const resizeQuality = 90;

/// 서버가 받는 한 장 최대 크기
const maxUploadBytes = 25 * 1024 * 1024;

/// 몇 번 절반으로 줄일지. 웹의 Math.floor(Math.log2(긴 변 / 2000))와 같다.
int halvingsFor(int width, int height) {
  final longSide = max(width, height);
  if (longSide < resizeMinSide * 2) return 0;
  return (log(longSide / resizeMinSide) / ln2).floor();
}

class PhotoPrepError implements Exception {
  const PhotoPrepError(this.message);
  final String message;
}

/// 고른 사진을 올릴 JPEG로 만든다: 웹과 같은 크기·품질로 줄이고, EXIF 회전을 픽셀에 반영하고, 메타데이터(GPS 등)는 뺀다.
///
/// 웹은 줄일 필요가 없는 사진을 원본 그대로 보내지만, 앱은 위치 정보를 지우려고 항상 다시 만든다(같은 크기, 품질 90).
/// 다시 만들지 못한 사진은 원본(위치 정보가 있을 수 있음)을 보내지 않고 오류로 알린다.
Future<Uint8List> preparePhoto(Uint8List original) async {
  final (width, height) = await _encodedSize(original);
  final halvings = halvingsFor(width, height);
  final factor = 1 << halvings;
  // 디코더가 2^n 배로 줄여 읽게 한다(inSampleSize). 웹처럼 2x2 평균으로 줄여 책 글씨에 물결무늬가 생기지 않는다.
  // 남은 확대·축소가 없도록 짧은 변 기준 최소 크기를 줄인 크기 그대로 준다(회전 여부와 상관없이 같은 값).
  final shortSide = max(1, min(width, height) ~/ factor);
  Uint8List result;
  try {
    result = await FlutterImageCompress.compressWithList(
      original,
      minWidth: shortSide,
      minHeight: shortSide,
      inSampleSize: factor,
      quality: resizeQuality,
      format: CompressFormat.jpeg,
      autoCorrectionAngle: true, // EXIF 회전 값대로 픽셀을 돌려 둔다(메타데이터를 지워도 똑바로 보이게).
      keepExif: false,
    );
  } catch (_) {
    throw const PhotoPrepError('이 사진은 열 수 없습니다. 다른 사진을 골라 주세요.');
  }
  final stripped = stripJpegMetadata(result);
  if (stripped == null || result.isEmpty) {
    throw const PhotoPrepError('이 사진은 열 수 없습니다. 다른 사진을 골라 주세요.');
  }
  if (stripped.length > maxUploadBytes) {
    throw const PhotoPrepError('사진은 한 장에 25MB까지 올릴 수 있습니다.');
  }
  return stripped;
}

/// 픽셀을 풀지 않고 크기만 읽는다(큰 사진도 메모리를 거의 쓰지 않는다).
Future<(int, int)> _encodedSize(Uint8List bytes) async {
  try {
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    final descriptor = await ui.ImageDescriptor.encoded(buffer);
    final size = (descriptor.width, descriptor.height);
    descriptor.dispose();
    buffer.dispose();
    return size;
  } catch (_) {
    throw const PhotoPrepError('이 사진은 열 수 없습니다. JPG, PNG, WebP, HEIC 사진을 골라 주세요.');
  }
}
