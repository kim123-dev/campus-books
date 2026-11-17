import 'dart:async';

import 'package:campus_books/api/api_client.dart';
import 'package:campus_books/api/token_storage.dart';
import 'package:campus_books/auth/auth_service.dart';
import 'package:campus_books/posts/post_form.dart';
import 'package:campus_books/posts/post_rules.dart';
import 'package:campus_books/providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api.dart';

FakeApi _api() => FakeApi({
      '/schools': (_) => jsonBody(200, {
            'items': [
              {'id': 1, 'name': '한빛대학교'},
            ],
          }),
      '/users/me/school': (_) => jsonBody(200, {
            'school': {'id': 1, 'name': '한빛대학교'},
            'changeable_at': null,
          }),
    });

Future<void> _pumpForm(WidgetTester tester, Future<void> Function(PostFormResult) onSubmit) async {
  tester.view.devicePixelRatio = 3;
  tester.view.physicalSize = const Size(1080, 7200); // 폭 360dp, 폼 전체가 보이게
  addTearDown(tester.view.reset);
  final api = _api();
  final session = Session(signedIn: true);
  final storage = MemoryTokenStorage(const TokenPair(accessToken: 'a', refreshToken: 'r'));
  await tester.pumpWidget(ProviderScope(
    overrides: [
      sessionProvider.overrideWithValue(session),
      tokenStorageProvider.overrideWithValue(storage),
      dioProvider.overrideWithValue(
        createApiDio(baseUrl: 'http://test', storage: storage, onSessionExpired: session.expire, adapter: api),
      ),
    ],
    child: MaterialApp(home: Scaffold(body: PostForm(submitLabel: '등록하기', onSubmit: onSubmit))),
  ));
  await settle(tester);
}

Future<void> _fillValid(WidgetTester tester) async {
  await tester.enterText(find.byKey(const Key('title')), '  자료구조 팝니다  ');
  await tester.enterText(find.byKey(const Key('book_title')), 'C로 배우는 자료구조');
  await tester.enterText(find.byKey(const Key('price')), '19900');
  await tester.tap(find.byKey(const Key('condition')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('상').last);
  await tester.pumpAndSettle();
}

void main() {
  test('글자 수는 서버(파이썬)처럼 문자 단위로 센다', () {
    // 설명 칸은 2000자에서 입력이 멈추지만, 규칙 자체도 서버와 같은지 확인한다.
    PostFormValues values(String description) =>
        PostFormValues(title: 't', bookTitle: 'b', condition: 'GOOD', price: '0', description: description);
    expect(validatePost(values('가' * 2001))['description'], '2000자 이하로 입력해 주세요.');
    expect(validatePost(values('😀' * 2000)), isEmpty); // 이모지 2000개 = 2000자(UTF-16으로는 4000)
    expect(validatePost(values('')), isEmpty); // 0원(무료 나눔)도 된다
  });

  testWidgets('빈 칸·범위를 넘는 값은 보내지 않고 칸마다 서버·웹과 같은 문구', (tester) async {
    var calls = 0;
    await _pumpForm(tester, (_) async => calls++);

    await tester.tap(find.byKey(const Key('post-submit')));
    await tester.pumpAndSettle();
    expect(find.text('내용을 입력해 주세요.'), findsNWidgets(2)); // 제목, 교재명 (공백만 넣어도 같음)
    expect(find.text('필수 항목입니다.'), findsNWidgets(2)); // 책 상태, 가격
    expect(find.text('입력값을 확인해 주세요.'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('title')), '   ');
    await tester.enterText(find.byKey(const Key('price')), '10000001');
    await tester.tap(find.byKey(const Key('post-submit')));
    await tester.pumpAndSettle();
    expect(find.text('10,000,000 이하여야 합니다.'), findsOneWidget);
    expect(calls, 0);

    // 가격 칸에는 숫자만 들어간다.
    await tester.enterText(find.byKey(const Key('price')), '1,000원');
    expect(find.text('1000'), findsOneWidget);
  });

  testWidgets('등록을 빠르게 두 번 눌러도 한 번만 보내고, 보내는 동안 버튼이 꺼진다', (tester) async {
    final results = <PostFormResult>[];
    final server = Completer<void>();
    await _pumpForm(tester, (result) {
      results.add(result);
      return server.future;
    });
    await _fillValid(tester);

    final button = find.byKey(const Key('post-submit'));
    await tester.tap(button);
    await tester.tap(button); // 아직 다시 그리기 전: 버튼이 눌리지만 무시되어야 한다
    await tester.pump();
    await tester.tap(button, warnIfMissed: false);
    await tester.pump();

    expect(results, hasLength(1));
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    expect(find.text('저장 중…'), findsOneWidget);
    final body = results.single.values.toJson();
    expect(body['title'], '자료구조 팝니다'); // 앞뒤 공백 제거
    expect(body['price'], 19900);
    expect(body['condition'], 'GOOD');
    expect(body['school_id'], 1); // 내 학교를 미리 고름(웹과 같음)
    expect(body['course_name'], isNull);

    server.complete();
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(button).onPressed, isNotNull);
    expect(find.text('등록하기'), findsOneWidget);
  });

  testWidgets('서버 오류 문구는 그대로: 422는 그 칸 아래, 그 밖은 아래 안내', (tester) async {
    var call = 0;
    await _pumpForm(tester, (_) async {
      call++;
      throw dioError(
        call == 1 ? 422 : 403,
        call == 1
            ? {
                'detail': [
                  {'type': 'value_error', 'loc': ['body', 'title'], 'msg': 'Value error, 서버가 정한 제목 문구'},
                ],
              }
            : {'detail': '2026년 11월 20일 15:00까지 이용이 정지되었습니다.'},
      );
    });
    await _fillValid(tester);
    await tester.tap(find.byKey(const Key('post-submit')));
    await tester.pumpAndSettle();
    expect(find.text('서버가 정한 제목 문구'), findsOneWidget);

    await tester.tap(find.byKey(const Key('post-submit')));
    await tester.pumpAndSettle();
    expect(find.text('2026년 11월 20일 15:00까지 이용이 정지되었습니다.'), findsOneWidget);
  });
}
