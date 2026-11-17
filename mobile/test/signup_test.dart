import 'package:campus_books/api/token_storage.dart';
import 'package:campus_books/auth/auth_service.dart';
import 'package:campus_books/auth/signup_rules.dart';
import 'package:campus_books/screens/signup_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api.dart';

const _question = '어릴 때 살던 동네에서 자주 가던 가게 이름은?';

FakeApi _api({Handler? signup}) => FakeApi({
      '/schools': (_) => jsonBody(200, {
            'items': [
              {'id': 1, 'name': '한빛대학교'},
            ],
          }),
      '/auth/security-questions': (_) => jsonBody(200, {
            'items': [
              {'key': 'CHILDHOOD_SHOP', 'text': _question},
            ],
          }),
      '/auth/signup': signup ?? (_) => jsonBody(201, {'id': 1}),
      '/auth/token': (_) => jsonBody(200, {'access_token': 'a', 'token_type': 'bearer', 'refresh_token': 'r'}),
    });

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(find.byKey(Key(key)), text);
}

Future<void> _submit(WidgetTester tester) async {
  final button = find.byKey(const Key('signup-submit'));
  await tester.ensureVisible(button);
  await tester.tap(button);
  await settle(tester);
}

Future<void> _chooseQuestion(WidgetTester tester, String text) async {
  await tester.ensureVisible(find.byKey(const Key('question')));
  await tester.tap(find.byKey(const Key('question')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(text).last);
  await tester.pumpAndSettle();
}

Future<void> _fillValid(WidgetTester tester) async {
  await _type(tester, 'email', 'new@campus.ac.kr');
  await _type(tester, 'password', 'password123');
  await _type(tester, 'password_confirm', 'password123');
  await _type(tester, 'nickname', '새내기');
  await _chooseQuestion(tester, _question);
  await _type(tester, 'answer', '해피 마트');
}

/// 폭은 휴대폰(360dp), 높이는 넉넉하게. ListView가 화면 밖 칸을 만들지 않아 찾지 못하는 일을 막는다.
void _tallPhone(WidgetTester tester) {
  tester.view.devicePixelRatio = 3;
  tester.view.physicalSize = const Size(1080, 7200);
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('잘못된 입력은 보내지 않고 칸마다 서버·웹과 같은 문구를 보여준다', (tester) async {
    _tallPhone(tester);
    final api = _api();
    await tester.pumpWidget(appWith(api, const SignupScreen()));
    await settle(tester);

    await _type(tester, 'email', 'not-an-email');
    await _type(tester, 'password', 'short');
    await _type(tester, 'password_confirm', 'different');
    await _type(tester, 'nickname', ' 가 ');
    await _submit(tester);

    expect(find.text('올바른 이메일 형식이 아닙니다.'), findsOneWidget);
    expect(find.text('8자 이상 입력해 주세요.'), findsOneWidget);
    expect(find.text('비밀번호가 일치하지 않습니다.'), findsOneWidget);
    expect(find.text('2자 이상 입력해 주세요.'), findsOneWidget); // 앞뒤 공백을 빼고 센다
    expect(find.text('질문을 골라 주세요.'), findsOneWidget);
    expect(find.text('답은 공백을 빼고 2자 이상이어야 합니다.'), findsOneWidget);

    // 직접 만든 질문이 짧거나, 답이 질문에 들어 있으면 막는다.
    await _chooseQuestion(tester, '직접 만들기');
    await _type(tester, 'custom_question', '좋아하는');
    await _submit(tester);
    expect(find.text('질문을 5자 이상 적어 주세요.'), findsOneWidget);

    await _type(tester, 'custom_question', '내가 좋아하는 과자는?');
    await _type(tester, 'answer', '과 자');
    await _submit(tester);
    expect(find.text('답이 질문 안에 그대로 들어 있어요. 질문만 보고 알 수 없는 답으로 정해 주세요.'), findsOneWidget);

    expect(api.sent('/auth/signup'), isEmpty);
  });

  testWidgets('학교가 하나면 미리 고르고, 가입이 성공하면 바로 로그인된다', (tester) async {
    _tallPhone(tester);
    final api = _api();
    final session = Session(signedIn: false);
    final storage = MemoryTokenStorage();
    await tester.pumpWidget(appWith(api, const SignupScreen(), session: session, storage: storage));
    await settle(tester);
    expect(find.text('한빛대학교'), findsOneWidget);

    await _fillValid(tester);
    await _submit(tester);

    final body = api.sent('/auth/signup').single.data as Map;
    expect(body['email'], 'new@campus.ac.kr');
    expect(body['school_id'], 1);
    expect(body['security_question'], {'question_key': 'CHILDHOOD_SHOP', 'answer': '해피 마트'});
    expect(api.sent('/auth/token'), hasLength(1));
    expect(session.signedIn, isTrue);
    expect((await storage.read())!.refreshToken, 'r');
  });

  testWidgets('서버 오류 문구는 그대로: 422는 그 칸 아래, 409는 아래 안내', (tester) async {
    _tallPhone(tester);
    var calls = 0;
    final api = _api(signup: (_) {
      calls++;
      if (calls == 1) {
        return jsonBody(422, {
          'detail': [
            {
              'type': 'value_error',
              'loc': ['body', 'email'],
              'msg': 'value is not a valid email address: The domain name x is not valid.',
            },
            {
              'type': 'value_error',
              'loc': ['body', 'security_question'],
              'msg': 'Value error, 서버가 정한 질문 오류 문구',
            },
          ],
        });
      }
      return jsonBody(409, {'detail': '이미 사용 중인 닉네임입니다.'});
    });
    await tester.pumpWidget(appWith(api, const SignupScreen()));
    await settle(tester);
    await _fillValid(tester);

    await _submit(tester);
    expect(find.text('올바른 이메일 형식이 아닙니다.'), findsOneWidget);
    expect(find.text('서버가 정한 질문 오류 문구'), findsOneWidget);

    await _submit(tester);
    expect(find.text('이미 사용 중인 닉네임입니다.'), findsOneWidget);
  });

  test('답 정리 규칙은 서버와 같다(NFKC·소문자·공백 제거)', () {
    expect(normalizeAnswer(' Happy  Mart '), 'happymart');
    expect(normalizeAnswer('ＡＢＣ　１２'), 'abc12'); // 전각 → 반각
    expect(validateSignup(SignupInput(
      email: 'a@b.kr',
      password: '가' * 25, // 25자지만 75바이트
      passwordConfirm: '가' * 25,
      nickname: '닉네임',
      questionKey: 'K',
      customQuestion: '',
      answer: '정답입니다',
    ))['password'], '비밀번호는 72바이트 이하여야 합니다.');
  });
}
