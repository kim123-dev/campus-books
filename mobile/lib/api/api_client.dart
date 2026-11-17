import 'package:dio/dio.dart';

import 'api_error.dart';
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

/// 화면에 보여줄 오류 문구 한 줄. (칸별 오류가 필요하면 ApiError.from을 쓴다)
String errorMessage(Object error) => ApiError.from(error).message;
