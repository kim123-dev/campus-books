import 'dart:typed_data';

/// JPEG에서 메타데이터 구역(APP1: EXIF·XMP — GPS 위치·기기 정보, APP13: IPTC)을 뺀다.
///
/// 압축 단계(flutter_image_compress, keepExif: false)도 EXIF를 남기지 않지만,
/// 플러그인 동작이 바뀌어도 위치 정보가 나가지 않도록 올리기 직전에 한 번 더 확인한다.
/// 그림 데이터(SOS 이후)는 건드리지 않는다. JPEG가 아니거나 구조가 이상하면 null(올리지 않는다).
Uint8List? stripJpegMetadata(Uint8List bytes) {
  if (bytes.length < 4 || bytes[0] != 0xFF || bytes[1] != 0xD8) return null;
  final out = BytesBuilder(copy: false)..add(const [0xFF, 0xD8]);
  var i = 2;
  while (i + 4 <= bytes.length) {
    if (bytes[i] != 0xFF) return null;
    final marker = bytes[i + 1];
    // 채움 바이트(0xFF 0xFF)는 건너뛴다.
    if (marker == 0xFF) {
      i++;
      continue;
    }
    // SOS(그림 데이터 시작)부터 끝까지는 그대로 붙인다.
    if (marker == 0xDA) {
      out.add(Uint8List.sublistView(bytes, i));
      return out.toBytes();
    }
    final length = (bytes[i + 2] << 8) | bytes[i + 3];
    final end = i + 2 + length;
    if (length < 2 || end > bytes.length) return null;
    final isMetadata = marker == 0xE1 || marker == 0xED;
    if (!isMetadata) out.add(Uint8List.sublistView(bytes, i, end));
    i = end;
  }
  return null;
}

/// 메타데이터 구역이 남아 있는지 (테스트·확인용)
bool hasJpegMetadata(Uint8List bytes) {
  var i = 2;
  while (i + 4 <= bytes.length && bytes[i] == 0xFF) {
    final marker = bytes[i + 1];
    if (marker == 0xDA) return false;
    if (marker == 0xE1 || marker == 0xED) return true;
    i += 2 + ((bytes[i + 2] << 8) | bytes[i + 3]);
  }
  return false;
}
