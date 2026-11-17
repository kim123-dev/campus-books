import 'dart:async';

import 'package:dio/dio.dart';

import 'token_storage.dart';

/// 이 표시가 붙은 요청은 토큰을 붙이지 않고, 401이 와도 갱신하지 않는다. (로그인·갱신·로그아웃)
const skipAuth = 'skipAuth';
const _retried = 'authRetried';

/// 요청에 액세스 토큰을 붙이고, 401이면 토큰을 갱신한 뒤 한 번 다시 보낸다.
///
/// 갱신은 한 번에 하나만 한다. 서버는 이미 쓴 refresh 토큰이 다시 오면 훔친 것으로 보고
/// 그 사용자의 모든 기기를 로그아웃시키므로, 같은 refresh 토큰으로 두 번 갱신하면 안 된다.
/// - 갱신 중에 401을 받은 요청은 진행 중인 갱신을 기다렸다가 새 토큰으로 다시 보낸다.
/// - 갱신이 끝난 뒤에 도착한 401(옛 토큰으로 보냈던 요청)은 다시 갱신하지 않고 새 토큰으로 다시 보낸다.
/// - 갱신이 401로 실패하면 저장된 토큰을 지우고 onSessionExpired를 부른다(로그인 화면으로).
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required this.storage,
    required this.refreshDio,
    required this.retryDio,
    required this.onSessionExpired,
  });

  final TokenStorage storage;

  /// 갱신 요청 전용(이 인터셉터가 없는 Dio). 갱신 요청이 다시 갱신을 부르지 않게.
  final Dio refreshDio;

  /// 새 토큰으로 다시 보낼 때 쓰는 Dio(보통 이 인터셉터가 달린 Dio).
  final Dio retryDio;

  final void Function() onSessionExpired;

  Future<String?>? _refreshing;

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    if (options.extra[skipAuth] != true) {
      final tokens = await storage.read();
      if (tokens != null) options.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final options = err.requestOptions;
    final usedToken = _bearer(options.headers['Authorization']);
    if (err.response?.statusCode != 401 ||
        options.extra[skipAuth] == true ||
        options.extra[_retried] == true ||
        usedToken == null) {
      return handler.next(err);
    }

    final accessToken = await freshAccessToken(usedToken);
    if (accessToken == null) return handler.next(err);

    options.extra[_retried] = true;
    options.headers['Authorization'] = 'Bearer $accessToken';
    try {
      handler.resolve(await retryDio.fetch(options));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  /// usedToken으로 보낸 요청이 401을 받았을 때 쓸 새 액세스 토큰. 다시 로그인해야 하면 null.
  /// 진행 중인 갱신이 있으면 새로 시작하지 않고 그 결과를 기다린다.
  /// (`??=`로 await 전에 바로 자리를 잡아, 동시에 들어온 401이 갱신을 두 번 시작하지 못하게 한다)
  Future<String?> freshAccessToken(String usedToken) {
    return _refreshing ??= _refresh(usedToken).whenComplete(() => _refreshing = null);
  }

  Future<String?> _refresh(String usedToken) async {
    final current = await storage.read();
    if (current == null) return null; // 그 사이 로그아웃됨
    // 다른 요청이 이미 갱신해 두었다. 옛 refresh 토큰을 다시 쓰지 않는다.
    if (current.accessToken != usedToken) return current.accessToken;

    final Response<dynamic> response;
    try {
      response = await refreshDio.post<dynamic>(
        '/auth/refresh',
        data: {'refresh_token': current.refreshToken},
        options: Options(extra: {skipAuth: true}),
      );
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        // 만료·폐기·정지·재사용 감지. 이 토큰으로는 더 할 수 있는 게 없다.
        await storage.clear();
        onSessionExpired();
      }
      // 그 밖(네트워크 오류, 5xx)은 토큰을 지우지 않는다. 다음 요청에서 다시 갱신해 본다.
      return null;
    }

    final tokens = TokenPair.fromJson(response.data as Map<String, dynamic>);
    // 갱신하는 동안 로그아웃했다면 받은 토큰을 저장하지 않는다(로그아웃한 사람이 다시 로그인되지 않게).
    final latest = await storage.read();
    if (latest?.refreshToken != current.refreshToken) return null;
    await storage.save(tokens);
    return tokens.accessToken;
  }

  static String? _bearer(Object? header) {
    if (header is! String || !header.startsWith('Bearer ')) return null;
    return header.substring('Bearer '.length);
  }
}
