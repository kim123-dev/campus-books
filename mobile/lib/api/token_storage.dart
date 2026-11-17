import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenPair {
  const TokenPair({required this.accessToken, required this.refreshToken});

  final String accessToken;
  final String refreshToken;

  /// /auth/token, /auth/refresh 응답 본문에서 만든다.
  factory TokenPair.fromJson(Map<String, dynamic> json) => TokenPair(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String,
      );
}

abstract class TokenStorage {
  Future<TokenPair?> read();
  Future<void> save(TokenPair tokens);
  Future<void> clear();
}

/// 안드로이드 Keystore로 암호화해 저장한다. 요청마다 Keystore를 읽지 않도록 메모리에도 둔다.
class SecureTokenStorage implements TokenStorage {
  SecureTokenStorage([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';

  final FlutterSecureStorage _storage;
  TokenPair? _cache;
  bool _loaded = false;

  @override
  Future<TokenPair?> read() async {
    if (_loaded) return _cache;
    final access = await _storage.read(key: _accessKey);
    final refresh = await _storage.read(key: _refreshKey);
    _cache = (access == null || refresh == null) ? null : TokenPair(accessToken: access, refreshToken: refresh);
    _loaded = true;
    return _cache;
  }

  @override
  Future<void> save(TokenPair tokens) async {
    // 메모리를 먼저 바꾼다. 바로 뒤에 오는 요청이 옛 토큰을 쓰지 않게.
    _cache = tokens;
    _loaded = true;
    await _storage.write(key: _accessKey, value: tokens.accessToken);
    await _storage.write(key: _refreshKey, value: tokens.refreshToken);
  }

  @override
  Future<void> clear() async {
    _cache = null;
    _loaded = true;
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}

/// 테스트용. 저장소 없이 메모리에만 둔다.
class MemoryTokenStorage implements TokenStorage {
  MemoryTokenStorage([this._tokens]);

  TokenPair? _tokens;

  @override
  Future<TokenPair?> read() async => _tokens;

  @override
  Future<void> save(TokenPair tokens) async => _tokens = tokens;

  @override
  Future<void> clear() async => _tokens = null;
}
