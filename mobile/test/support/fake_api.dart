import 'dart:convert';
import 'dart:typed_data';

import 'package:campus_books/api/api_client.dart';
import 'package:campus_books/api/token_storage.dart';
import 'package:campus_books/auth/auth_service.dart';
import 'package:campus_books/providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

typedef Handler = ResponseBody Function(RequestOptions options);

/// 경로별로 응답을 정해 두는 가짜 서버. 보낸 요청을 기록한다. 없는 경로는 네트워크 오류.
class FakeApi implements HttpClientAdapter {
  FakeApi(this.handlers);

  final Map<String, Handler> handlers;
  final List<RequestOptions> requests = [];

  List<RequestOptions> sent(String path) => requests.where((r) => r.path == path).toList();

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    requests.add(options);
    final handler = handlers[options.path];
    if (handler == null) throw DioException.connectionError(requestOptions: options, reason: 'offline');
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody jsonBody(int status, Object body, {Map<String, List<String>> headers = const {}}) {
  return ResponseBody.fromString(jsonEncode(body), status, headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
    ...headers,
  });
}

/// 화면 하나를 가짜 서버와 함께 띄운다.
Widget appWith(FakeApi api, Widget screen, {Session? session, TokenStorage? storage}) {
  final theSession = session ?? Session(signedIn: false);
  final theStorage = storage ?? MemoryTokenStorage();
  return ProviderScope(
    overrides: [
      sessionProvider.overrideWithValue(theSession),
      tokenStorageProvider.overrideWithValue(theStorage),
      dioProvider.overrideWithValue(createApiDio(
        baseUrl: 'http://test',
        storage: theStorage,
        onSessionExpired: theSession.expire,
        adapter: api,
      )),
    ],
    child: MaterialApp(home: screen),
  );
}

/// dio 응답 처리는 실제 비동기 작업이 섞여 있어 가짜 시계(pump)만으로는 끝나지 않는다. 잠깐 실제로 기다린다.
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pumpAndSettle();
  }
}
