import 'dart:async';

import 'package:campus_books/api/token_storage.dart';
import 'package:campus_books/auth/auth_service.dart';
import 'package:campus_books/posts/post_api.dart';
import 'package:campus_books/posts/post_models.dart';
import 'package:campus_books/providers.dart';
import 'package:campus_books/screens/home_screen.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// 요청마다 응답을 직접 풀어 주는 가짜 목록 API. 어떤 순서로 응답이 오는지 테스트가 정한다.
class ControlledPostApi extends PostApi {
  ControlledPostApi() : super(Dio());

  final List<(PostQuery, int, Completer<PostPage>)> calls = [];

  @override
  Future<PostPage> list(PostQuery query, int page) {
    final completer = Completer<PostPage>();
    calls.add((query, page, completer));
    return completer.future;
  }

  /// 검색어가 q인 가장 최근 요청에 [titles] 글로 응답한다.
  void answer(String q, List<String> titles, {int total = -1}) {
    final call = calls.lastWhere((c) => c.$1.q == q && !c.$3.isCompleted);
    call.$3.complete(PostPage(
      items: [for (final (i, t) in titles.indexed) _post(call.$2 * 100 + i, t)],
      total: total < 0 ? titles.length : total,
      page: call.$2,
    ));
  }
}

PostSummary _post(int id, String title) => PostSummary(
      id: id,
      title: title,
      bookTitle: title,
      courseName: null,
      condition: 'GOOD',
      price: 12000,
      status: 'ON_SALE',
      sellerId: 1,
      sellerNickname: '판매자',
      thumbnailUrl: null,
      schoolName: null,
      createdAt: DateTime.utc(2026, 11, 17),
    );

Future<ControlledPostApi> _pumpHome(WidgetTester tester) async {
  final api = ControlledPostApi();
  final session = Session(signedIn: false);
  final storage = MemoryTokenStorage();
  await tester.pumpWidget(ProviderScope(
    overrides: [
      sessionProvider.overrideWithValue(session),
      tokenStorageProvider.overrideWithValue(storage),
      dioProvider.overrideWithValue(Dio(BaseOptions(baseUrl: 'http://test'))),
      postApiProvider.overrideWithValue(api),
    ],
    child: const MaterialApp(home: HomeScreen()),
  ));
  return api;
}

void main() {
  testWidgets('입력이 멈추고 0.4초 뒤에 한 번만 검색한다', (tester) async {
    final api = await _pumpHome(tester);
    api.answer('', ['처음 목록']);
    await tester.pump();

    await tester.enterText(find.byKey(const Key('search')), '자');
    await tester.pump(const Duration(milliseconds: 200));
    await tester.enterText(find.byKey(const Key('search')), '자료');
    await tester.pump(const Duration(milliseconds: 399));
    expect(api.calls, hasLength(1)); // 아직 처음 목록 요청뿐

    await tester.pump(const Duration(milliseconds: 1));
    expect(api.calls.map((c) => c.$1.q), ['', '자료']); // "자"는 보내지 않았다
    // 판매 완료는 기본으로 숨긴다(include_sold=false).
    expect(api.calls.every((c) => !c.$1.includeSold), isTrue);
  });

  testWidgets('이전 검색 결과가 늦게 와도 지금 검색 결과를 덮어쓰지 않는다', (tester) async {
    final api = await _pumpHome(tester);
    api.answer('', ['처음 목록']);
    await tester.pump();

    await tester.enterText(find.byKey(const Key('search')), '자료');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.enterText(find.byKey(const Key('search')), '자료구조');
    await tester.pump(const Duration(milliseconds: 400));
    expect(api.calls.map((c) => c.$1.q), ['', '자료', '자료구조']);

    // 나중 검색이 먼저 도착하고, 앞의 검색이 늦게 도착한다.
    api.answer('자료구조', ['자료구조 새 책']);
    await tester.pump();
    api.answer('자료', ['자료 늦은 결과']);
    await tester.pump();

    expect(find.text('자료구조 새 책'), findsOneWidget);
    expect(find.text('자료 늦은 결과'), findsNothing);
  });

  testWidgets('검색을 바꾼 뒤 도착한 이전 검색의 다음 페이지도 버린다', (tester) async {
    tester.view.devicePixelRatio = 3;
    tester.view.physicalSize = const Size(1080, 7200); // 목록 끝이 바로 보여 다음 페이지를 부른다
    addTearDown(tester.view.reset);
    final api = await _pumpHome(tester);
    api.answer('', ['1쪽 글'], total: 40);
    await tester.pump();
    await tester.pump();
    expect(api.calls.last.$2, 2); // 2쪽 요청 중

    await tester.enterText(find.byKey(const Key('search')), '물리');
    await tester.pump(const Duration(milliseconds: 400));
    api.answer('물리', ['물리 결과']);
    await tester.pump();
    api.answer('', ['2쪽 늦은 글'], total: 40);
    await tester.pump();

    expect(find.text('물리 결과'), findsOneWidget);
    expect(find.text('2쪽 늦은 글'), findsNothing);
    expect(find.text('1쪽 글'), findsNothing);
  });
}
