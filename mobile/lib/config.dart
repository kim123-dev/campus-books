import 'package:flutter/foundation.dart';

/// 서버 주소는 여기 한 곳에서만 정한다.
/// 기본값은 운영 서버. PC의 로컬 서버에 붙을 때는
///   flutter run --dart-define=API_BASE=http://10.0.2.2:8000
/// (10.0.2.2 = 에뮬레이터에서 본 PC. 평문 http는 디버그 빌드에서만 허용된다)
const productionApiBase = 'https://campus-books.up.railway.app';

const _definedApiBase = String.fromEnvironment('API_BASE');

String get apiBase {
  final base = _definedApiBase.isEmpty ? productionApiBase : _definedApiBase;
  // 릴리스는 https만. 실수로 http 주소로 빌드하면 바로 알 수 있게 시작할 때 멈춘다.
  // (안드로이드 네트워크 보안 설정도 릴리스에서 평문을 막지만, 원인을 알기 쉽게 한 번 더 확인)
  if (kReleaseMode && !base.startsWith('https://')) {
    throw StateError('릴리스 빌드는 https 서버 주소만 쓸 수 있습니다: $base');
  }
  return base;
}
