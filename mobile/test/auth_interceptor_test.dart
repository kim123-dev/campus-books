import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:campus_books/api/api_client.dart';
import 'package:campus_books/api/token_storage.dart';
import 'package:campus_books/auth/auth_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

/// 서버 흉내: 유효한 액세스 토큰은 하나뿐이고, /auth/refresh는 refresh 토큰을 한 번만 받아 준다(재사용이면 401).
class FakeServer implements HttpClientAdapter {
  String validAccess = 'access-2';
  String validRefresh = 'refresh-1';
  int refreshCalls = 0;
  bool refreshRejects = false;

  /// 열어 두면 /auth/refresh 응답이 열릴 때까지 멈춘다. (갱신 중에 다른 요청을 보내 보려고)
  Completer<void>? refreshGate;

  /// 열어 두면 /slow 요청이 열릴 때까지 멈춘다. (옛 토큰으로 보낸 요청이 늦게 401을 받는 경우)
  Completer<void>? slowGate;
  bool slowArrived = false;

  final List<String> dataAuthHeaders = [];
  final List<String> logoutCalls = [];
  TokenStorage? storageAtLogout;
  TokenPair? tokensSeenAtLogout;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    switch (options.path) {
      case '/auth/refresh':
        refreshCalls++;
        await refreshGate?.future;
        final sent = (options.data as Map)['refresh_token'];
        if (refreshRejects || sent != validRefresh) {
          return _json(401, {'detail': '로그인이 만료되었습니다. 다시 로그인해 주세요.'});
        }
        validAccess = 'access-${refreshCalls + 2}';
        validRefresh = 'refresh-${refreshCalls + 1}';
        return _json(200, {'access_token': validAccess, 'token_type': 'bearer', 'refresh_token': validRefresh});
      case '/auth/logout':
        tokensSeenAtLogout = await storageAtLogout?.read();
        logoutCalls.add((options.data as Map)['refresh_token'] as String);
        return ResponseBody.fromString('', 204);
      case '/slow':
        slowArrived = true;
        await slowGate?.future;
        return _protected(options);
      case '/always-401':
        dataAuthHeaders.add(options.headers['Authorization'] as String? ?? '');
        return _json(401, {'detail': '권한이 없습니다.'});
      default:
        return _protected(options);
    }
  }

  ResponseBody _protected(RequestOptions options) {
    final header = options.headers['Authorization'] as String? ?? '';
    dataAuthHeaders.add(header);
    if (header == 'Bearer $validAccess') return _json(200, {'ok': true});
    return _json(401, {'detail': '로그인이 필요합니다.'});
  }

  static ResponseBody _json(int status, Object body) => ResponseBody.fromString(
        jsonEncode(body),
        status,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );

  @override
  void close({bool force = false}) {}
}

void main() {
  late FakeServer server;
  late MemoryTokenStorage storage;
  late int expiredCalls;
  late Dio dio;

  setUp(() {
    server = FakeServer();
    // 저장된 액세스 토큰(access-1)은 이미 만료됐다. 서버가 받아 주는 건 access-2부터.
    storage = MemoryTokenStorage(const TokenPair(accessToken: 'access-1', refreshToken: 'refresh-1'));
    expiredCalls = 0;
    dio = createApiDio(
      baseUrl: 'http://test',
      storage: storage,
      onSessionExpired: () => expiredCalls++,
      adapter: server,
    );
  });

  test('동시에 401을 받은 요청 여러 개는 갱신을 한 번만 하고 모두 새 토큰으로 다시 보낸다', () async {
    final responses = await Future.wait([for (var i = 0; i < 5; i++) dio.get<dynamic>('/data/$i')]);

    expect(responses.map((r) => r.statusCode), everyElement(200));
    expect(server.refreshCalls, 1);
    final tokens = await storage.read();
    expect(tokens!.accessToken, 'access-3');
    expect(tokens.refreshToken, 'refresh-2');
    // 처음 5번은 옛 토큰, 다시 보낸 5번은 새 토큰
    expect(server.dataAuthHeaders.where((h) => h == 'Bearer access-1').length, 5);
    expect(server.dataAuthHeaders.where((h) => h == 'Bearer access-3').length, 5);
    expect(expiredCalls, 0);
  });

  test('갱신하는 동안 새로 401을 받은 요청은 기다렸다가 새 토큰으로 다시 보낸다', () async {
    server.refreshGate = Completer<void>();
    final first = dio.get<dynamic>('/data/first');
    await _until(() => server.refreshCalls == 1);

    // 갱신이 멈춰 있는 동안 보낸 요청: 아직 옛 토큰이 붙어 401 → 진행 중인 갱신을 기다린다.
    final second = dio.get<dynamic>('/data/second');
    await _until(() => server.dataAuthHeaders.length == 2);
    expect(server.refreshCalls, 1);

    server.refreshGate!.complete();
    final results = await Future.wait([first, second]);
    expect(results.map((r) => r.statusCode), [200, 200]);
    expect(server.refreshCalls, 1);
  });

  test('갱신이 끝난 뒤 늦게 401을 받은 요청은 다시 갱신하지 않고 새 토큰으로 다시 보낸다', () async {
    server.slowGate = Completer<void>();
    final slow = dio.get<dynamic>('/slow'); // 옛 토큰(access-1)을 붙인 채 서버에서 멈춤
    await _until(() => server.slowArrived);

    expect((await dio.get<dynamic>('/data')).statusCode, 200); // 여기서 갱신 1번
    expect(server.refreshCalls, 1);

    server.slowGate!.complete();
    expect((await slow).statusCode, 200);
    // 옛 refresh 토큰을 다시 보냈다면 서버가 재사용으로 보고 401을 줬을 것이다.
    expect(server.refreshCalls, 1);
    expect(expiredCalls, 0);
  });

  test('갱신이 401이면 저장된 토큰을 지우고 로그인 화면으로 보낸다(한 번만)', () async {
    server.refreshRejects = true;
    final results = await Future.wait([
      for (var i = 0; i < 3; i++)
        dio.get<dynamic>('/data/$i').then<Object>((r) => r, onError: (Object e) => e),
    ]);

    for (final result in results) {
      expect(result, isA<DioException>());
      expect((result as DioException).response?.statusCode, 401);
    }
    expect(server.refreshCalls, 1);
    expect(await storage.read(), isNull);
    expect(expiredCalls, 1);
  });

  test('갱신이 네트워크 오류면 토큰을 지우지 않는다', () async {
    final failing = createApiDio(
      baseUrl: 'http://test',
      storage: storage,
      onSessionExpired: () => expiredCalls++,
      adapter: _FailingRefresh(server),
    );
    await expectLater(failing.get<dynamic>('/data'), throwsA(isA<DioException>()));
    expect(await storage.read(), isNotNull);
    expect(expiredCalls, 0);
  });

  test('다시 보낸 요청도 401이면 더 갱신하지 않고 실패한다', () async {
    // 갱신은 되지만 이 주소는 계속 401
    final result = await dio.get<dynamic>('/always-401').then<Object>((r) => r, onError: (Object e) => e);
    expect((result as DioException).response?.statusCode, 401);
    expect(server.refreshCalls, 1);
    expect(server.dataAuthHeaders, ['Bearer access-1', 'Bearer access-3']);
  });

  test('로그아웃은 저장된 토큰을 먼저 지운 뒤 /auth/logout을 부른다', () async {
    final session = Session(signedIn: true);
    server.storageAtLogout = storage;
    await AuthService(dio: dio, storage: storage, session: session).logout();

    expect(server.logoutCalls, ['refresh-1']);
    expect(server.tokensSeenAtLogout, isNull); // 서버에 알릴 때는 이미 지워져 있었다
    expect(await storage.read(), isNull);
    expect(session.signedIn, isFalse);
  });

  test('로그아웃 요청이 실패해도 이 기기에서는 로그아웃된다', () async {
    final session = Session(signedIn: true);
    final offline = Dio()..httpClientAdapter = _Offline();
    await AuthService(dio: offline, storage: storage, session: session).logout();
    expect(await storage.read(), isNull);
    expect(session.signedIn, isFalse);
  });
}

Future<void> _until(bool Function() condition) async {
  for (var i = 0; i < 200 && !condition(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 1));
  }
  expect(condition(), isTrue);
}

class _FailingRefresh implements HttpClientAdapter {
  _FailingRefresh(this.inner);

  final FakeServer inner;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) {
    if (options.path == '/auth/refresh') {
      throw DioException.connectionError(requestOptions: options, reason: 'offline');
    }
    return inner.fetch(options, requestStream, cancelFuture);
  }

  @override
  void close({bool force = false}) {}
}

class _Offline implements HttpClientAdapter {
  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) {
    throw DioException.connectionError(requestOptions: options, reason: 'offline');
  }

  @override
  void close({bool force = false}) {}
}
