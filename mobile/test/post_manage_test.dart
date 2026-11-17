import 'dart:convert';

import 'package:campus_books/api/token_storage.dart';
import 'package:campus_books/auth/auth_service.dart';
import 'package:campus_books/posts/post_events.dart';
import 'package:campus_books/providers.dart';
import 'package:campus_books/screens/post_detail_screen.dart';
import 'package:campus_books/screens/post_edit_screen.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api.dart';

Map<String, dynamic> _post({List<Map<String, dynamic>> images = const []}) => {
      'id': 5,
      'title': '자료구조 팝니다',
      'book_title': 'C로 배우는 자료구조',
      'course_name': '자료구조',
      'condition': 'FAIR',
      'price': 15000,
      'description': '필기 조금 있어요',
      'status': 'ON_SALE',
      'seller': {'id': 7, 'nickname': '판매자'},
      'school': {'id': 1, 'name': '한빛대학교'},
      'thumbnail_url': null,
      'created_at': '2026-11-17T10:00:00',
      'open_chat_url': null,
      'images': images,
    };

FakeApi _api(Map<String, dynamic> post) => FakeApi({
      '/posts/5': (options) => switch (options.method) {
            'GET' => jsonBody(200, post),
            'PATCH' => jsonBody(200, {...post, 'title': (options.data as Map)['title']}),
            'DELETE' => ResponseBody.fromString('', 204),
            _ => jsonBody(405, {'detail': 'no'}),
          },
      '/users/me': (_) => jsonBody(200, {'id': 7, 'nickname': '판매자', 'email': 'me@campus.ac.kr'}),
      '/schools': (_) => jsonBody(200, {
            'items': [
              {'id': 1, 'name': '한빛대학교'},
            ],
          }),
      '/users/me/school': (_) => jsonBody(200, {'school': null, 'changeable_at': null}),
    });

/// 목록 자리(첫 화면)에서 [screen]을 열어 둔다. 저장·삭제 뒤 목록으로 돌아오는지 보려고.
Future<void> _open(WidgetTester tester, FakeApi api, Widget screen) async {
  tester.view.devicePixelRatio = 3;
  tester.view.physicalSize = const Size(1080, 7200); // 폭 360dp, 폼 전체가 보이게
  addTearDown(tester.view.reset);
  final storage = MemoryTokenStorage(const TokenPair(accessToken: 'a', refreshToken: 'r'));
  await tester.pumpWidget(appWith(
    api,
    Builder(
      builder: (context) => Scaffold(
        body: Center(
          child: TextButton(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen)),
            child: const Text('목록'),
          ),
        ),
      ),
    ),
    session: Session(signedIn: true),
    storage: storage,
  ));
  await tester.tap(find.text('목록'));
  await settle(tester);
}

String _field(WidgetTester tester, String key) => tester.widget<TextField>(find.byKey(Key(key))).controller!.text;

void main() {
  testWidgets('수정 폼에 지금 내용·사진·학교가 채워지고, 저장은 웹과 같은 PATCH 본문', (tester) async {
    final api = _api(_post(images: [
      {'id': 11, 'url': '/images/a.webp', 'thumbnail_url': '/images/a_thumb.webp'},
    ]));
    await _open(tester, api, const PostEditScreen(postId: 5));

    expect(_field(tester, 'title'), '자료구조 팝니다');
    expect(_field(tester, 'book_title'), 'C로 배우는 자료구조');
    expect(_field(tester, 'course_name'), '자료구조');
    expect(_field(tester, 'price'), '15000');
    expect(_field(tester, 'description'), '필기 조금 있어요');
    expect(find.text('중'), findsOneWidget); // 책 상태 FAIR
    expect(find.text('한빛대학교'), findsOneWidget);
    expect(find.bySemanticsLabel('올린 사진 1'), findsOneWidget);
    expect(find.text('1/3'), findsOneWidget);

    // 올린 사진 1장을 빼고 제목을 고쳐 저장한다.
    await tester.tap(find.byTooltip('올린 사진 1 빼기'));
    await tester.pump();
    expect(find.text('삭제 예정'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('title')), '자료구조 싸게 팝니다');
    await tester.tap(find.byKey(const Key('post-submit')));
    await settle(tester);

    final patch = api.sent('/posts/5').where((r) => r.method == 'PATCH').single;
    final body = jsonDecode(jsonEncode(patch.data)) as Map<String, dynamic>;
    expect(body, containsPair('title', '자료구조 싸게 팝니다'));
    expect(body, containsPair('price', 15000));
    expect(body, containsPair('condition', 'FAIR'));
    expect(body, containsPair('school_id', 1)); // 학교도 그대로 보낸다(비우면 null로 해제)
    expect(body['remove_image_ids'], [11]);
    expect(body['add_image_ids'], isEmpty);
    expect(body.containsKey('image_ids'), isFalse);

    // 저장하면 수정 화면이 닫힌다(뒤로 가기 확인 창 없이).
    expect(find.byType(PostEditScreen), findsNothing);
    expect(find.text('수정했습니다.'), findsOneWidget);
  });

  testWidgets('삭제는 확인 창을 거치고, 지우면 상세에서 나와 목록에서도 빠지게 알린다', (tester) async {
    final api = _api(_post());
    await _open(tester, api, const PostDetailScreen(postId: 5));
    final events = ProviderScope.containerOf(tester.element(find.byType(PostDetailScreen))).read(postEventsProvider);

    // 취소하면 지우지 않는다.
    await tester.tap(find.byKey(const Key('delete-post')));
    await tester.pumpAndSettle();
    expect(find.text('이 글을 삭제할까요?'), findsOneWidget);
    expect(find.text('삭제한 글은 되돌릴 수 없습니다.'), findsOneWidget);
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();
    expect(api.sent('/posts/5').where((r) => r.method == 'DELETE'), isEmpty);
    expect(find.byType(PostDetailScreen), findsOneWidget);

    await tester.tap(find.byKey(const Key('delete-post')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirm-action')));
    await settle(tester);

    expect(api.sent('/posts/5').where((r) => r.method == 'DELETE'), hasLength(1));
    expect(events.value?.kind, PostEventKind.deleted);
    expect(events.value?.id, 5);
    expect(find.byType(PostDetailScreen), findsNothing);
    expect(find.text('글을 삭제했습니다.'), findsOneWidget);
  });
}
