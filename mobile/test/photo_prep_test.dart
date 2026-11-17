import 'dart:convert';
import 'dart:typed_data';

import 'package:campus_books/photos/jpeg_metadata.dart';
import 'package:campus_books/photos/photo_prep.dart';
import 'package:flutter_test/flutter_test.dart';

List<int> _segment(int marker, List<int> payload) {
  final length = payload.length + 2;
  return [0xFF, marker, length >> 8, length & 0xFF, ...payload];
}

void main() {
  test('줄이는 횟수는 웹과 같다(긴 변이 2000px 아래로 내려가지 않는 데까지 절반씩)', () {
    expect(halvingsFor(1600, 1200), 0);
    expect(halvingsFor(3999, 3000), 0);
    expect(halvingsFor(4000, 3000), 1); // → 2000x1500
    expect(halvingsFor(3000, 4032), 1); // 세로 사진도 긴 변 기준 → 1500x2016
    expect(halvingsFor(8000, 6000), 2); // → 2000x1500
    expect(halvingsFor(12000, 9000), 2); // → 3000x2250
  });

  test('EXIF(GPS)·IPTC 구역은 빼고 나머지 JPEG 구조와 그림 데이터는 그대로 둔다', () {
    final exif = _segment(0xE1, [...ascii.encode('Exif'), 0, 0, ...ascii.encode('GPS 37.5665N 126.9780E')]);
    final jfif = _segment(0xE0, [...ascii.encode('JFIF'), 0, 1, 1, 0, 0, 1, 0, 1, 0, 0]);
    final iptc = _segment(0xED, ascii.encode('Photoshop 3.0'));
    final quant = _segment(0xDB, List.filled(65, 1));
    final scan = [0xFF, 0xDA, 0x00, 0x08, 1, 2, 3, 4, 5, 6, 0x12, 0x34, 0xFF, 0xD9];
    final jpeg = Uint8List.fromList([0xFF, 0xD8, ...jfif, ...exif, ...iptc, ...quant, ...scan]);
    expect(hasJpegMetadata(jpeg), isTrue);

    final stripped = stripJpegMetadata(jpeg)!;
    expect(hasJpegMetadata(stripped), isFalse);
    expect(stripped, [0xFF, 0xD8, ...jfif, ...quant, ...scan]);
    expect(ascii.decode(stripped, allowInvalid: true).contains('GPS'), isFalse);
  });

  test('JPEG가 아니거나 깨졌으면 null(원본을 올리지 않는다)', () {
    expect(stripJpegMetadata(Uint8List.fromList(ascii.encode('not a jpeg'))), isNull);
    expect(stripJpegMetadata(Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE1, 0x00, 0xFF])), isNull);
  });
}
