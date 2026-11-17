import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../api/auth_interceptor.dart';
import '../api/token_storage.dart';

/// 로그인 상태. 라우터가 듣고 있다가 로그아웃·만료 때 로그인 화면으로 보낸다.
class Session extends ChangeNotifier {
  Session({required bool signedIn}) : _signedIn = signedIn; // ignore: prefer_initializing_formals

  bool _signedIn;
  bool _expired = false;

  bool get signedIn => _signedIn;

  /// 갱신이 거절되어 로그아웃된 경우. 로그인 화면에서 안내한다.
  bool get expired => _expired;

  void signIn() {
    _signedIn = true;
    _expired = false;
    notifyListeners();
  }

  void signOut({bool expired = false}) {
    if (!_signedIn && _expired == expired) return;
    _signedIn = false;
    _expired = expired;
    notifyListeners();
  }

  void expire() => signOut(expired: true);
}

class AuthService {
  AuthService({required this.dio, required this.storage, required this.session});

  final Dio dio;
  final TokenStorage storage;
  final Session session;

  Future<void> login(String email, String password) async {
    final response = await dio.post<dynamic>(
      '/auth/token',
      data: {'username': email.trim(), 'password': password, 'device_name': 'Android'},
      options: Options(contentType: Headers.formUrlEncodedContentType, extra: {skipAuth: true}),
    );
    await storage.save(TokenPair.fromJson(response.data as Map<String, dynamic>));
    session.signIn();
  }

  /// 저장된 토큰을 먼저 지운 뒤 서버에 알린다.
  /// 서버 호출이 실패해도(오프라인 등) 이 기기에서는 확실히 로그아웃된다.
  Future<void> logout() async {
    final tokens = await storage.read();
    await storage.clear();
    session.signOut();
    if (tokens == null) return;
    try {
      await dio.post<dynamic>(
        '/auth/logout',
        data: {'refresh_token': tokens.refreshToken},
        options: Options(extra: {skipAuth: true}),
      );
    } on DioException {
      // 서버의 refresh 토큰은 30일 뒤 만료된다. 여기서 더 할 일은 없다.
    }
  }
}
