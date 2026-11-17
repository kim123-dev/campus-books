import 'package:dio/dio.dart';

import 'auth_interceptor.dart';
import 'token_storage.dart';

/// 앱 전체가 쓰는 Dio. 테스트에서는 adapter로 가짜 서버를 끼운다.
Dio createApiDio({
  required String baseUrl,
  required TokenStorage storage,
  required void Function() onSessionExpired,
  HttpClientAdapter? adapter,
}) {
  final options = BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
  );
  final dio = Dio(options);
  final refreshDio = Dio(options);
  if (adapter != null) {
    dio.httpClientAdapter = adapter;
    refreshDio.httpClientAdapter = adapter;
  }
  dio.interceptors.add(AuthInterceptor(
    storage: storage,
    refreshDio: refreshDio,
    retryDio: dio,
    onSessionExpired: onSessionExpired,
  ));
  return dio;
}

/// 서버의 {"detail": "..."} 메시지. 없으면 fallback.
String errorMessage(Object error, {String fallback = '잠시 후 다시 시도해 주세요.'}) {
  if (error is DioException) {
    final data = error.response?.data;
    if (data is Map && data['detail'] is String) return data['detail'] as String;
    if (error.response == null) return '서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.';
  }
  return fallback;
}
