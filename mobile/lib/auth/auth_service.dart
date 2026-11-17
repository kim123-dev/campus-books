import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../api/auth_interceptor.dart';
import '../api/token_storage.dart';
import 'signup_rules.dart';

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

  /// 만료 안내를 보고 로그인 없이 둘러보기로 한 경우
  void clearExpired() {
    if (!_expired) return;
    _expired = false;
    notifyListeners();
  }
}

class AuthService {
  AuthService({required this.dio, required this.storage, required this.session});

  final Dio dio;
  final TokenStorage storage;
  final Session session;

  // 내 사용자 번호. 상세에서 내 글인지 볼 때마다 /users/me를 부르지 않도록 한 번만 받아 둔다.
  int? _myId;

  Future<void> login(String email, String password) async {
    final response = await dio.post<dynamic>(
      '/auth/token',
      data: {'username': email.trim(), 'password': password, 'device_name': 'Android'},
      options: Options(contentType: Headers.formUrlEncodedContentType, extra: {skipAuth: true}),
    );
    await storage.save(TokenPair.fromJson(response.data as Map<String, dynamic>));
    _myId = null;
    session.signIn();
  }

  /// 가입한 뒤 바로 로그인한다. 가입은 됐는데 로그인이 실패하면(드묾) SignedUpButLoginFailed.
  Future<void> signup(SignupInput input) async {
    await dio.post<dynamic>('/auth/signup', data: input.toJson(), options: Options(extra: {skipAuth: true}));
    try {
      await login(input.email, input.password);
    } on DioException catch (e) {
      throw SignedUpButLoginFailed(e);
    }
  }

  /// 로그인한 사용자의 번호. 로그인하지 않았거나 확인하지 못하면 null(그래도 화면은 그대로 보여준다).
  Future<int?> myId() async {
    if (!session.signedIn || await storage.read() == null) return null;
    if (_myId != null) return _myId;
    try {
      final response = await dio.get<dynamic>('/users/me');
      return _myId = (response.data as Map)['id'] as int;
    } on DioException {
      return null;
    }
  }

  /// 가입 화면의 학교 목록(활성 학교만, 로그인 불필요)
  Future<List<School>> schools() async {
    final response = await dio.get<dynamic>('/schools', options: Options(extra: {skipAuth: true}));
    return [
      for (final item in (response.data as Map)['items'] as List)
        School(id: (item as Map)['id'] as int, name: item['name'] as String),
    ];
  }

  /// 가입 화면의 본인 확인 질문 목록
  Future<List<SecurityQuestion>> securityQuestions() async {
    final response = await dio.get<dynamic>('/auth/security-questions', options: Options(extra: {skipAuth: true}));
    return [
      for (final item in (response.data as Map)['items'] as List)
        SecurityQuestion(key: (item as Map)['key'] as String, text: item['text'] as String),
    ];
  }

  /// 저장된 토큰을 먼저 지운 뒤 서버에 알린다.
  /// 서버 호출이 실패해도(오프라인 등) 이 기기에서는 확실히 로그아웃된다.
  Future<void> logout() async {
    final tokens = await storage.read();
    await storage.clear();
    _myId = null;
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

class School {
  const School({required this.id, required this.name});
  final int id;
  final String name;
}

class SecurityQuestion {
  const SecurityQuestion({required this.key, required this.text});
  final String key;
  final String text;
}

/// 가입은 성공했지만 이어서 한 로그인이 실패함. 가입 화면을 다시 보여주지 않고 로그인 화면으로 보낸다.
class SignedUpButLoginFailed implements Exception {
  const SignedUpButLoginFailed(this.cause);
  final DioException cause;
}
