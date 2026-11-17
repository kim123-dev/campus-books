import 'package:campus_books/screens/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api.dart';

Future<String> _loginError(WidgetTester tester, FakeApi api) async {
  await tester.pumpWidget(appWith(api, const LoginScreen()));
  await tester.enterText(find.byType(TextField).at(0), 'student@campus.ac.kr');
  await tester.enterText(find.byType(TextField).at(1), 'wrong-password');
  await tester.tap(find.byType(FilledButton));
  await settle(tester);
  return tester.widget<Text>(find.byKey(const Key('login-error'))).data!;
}

void main() {
  testWidgets('429면 Retry-After로 기다릴 시간을 분으로 알려준다', (tester) async {
    final api = FakeApi({
      '/auth/token': (_) => jsonBody(
            429,
            {'detail': '로그인 실패가 너무 많습니다. 잠시 후 다시 시도해 주세요.'},
            headers: {
              'retry-after': ['281'],
            },
          ),
    });
    expect(await _loginError(tester, api), '로그인 시도가 너무 많습니다. 잠시 후(약 5분) 다시 시도해 주세요.');
  });

  testWidgets('403(정지)은 서버 문구, 네트워크 오류는 연결 확인 안내', (tester) async {
    final suspended = FakeApi({
      '/auth/token': (_) => jsonBody(403, {'detail': '2026년 11월 20일 15:00까지 이용이 정지되었습니다.'}),
    });
    expect(await _loginError(tester, suspended), '2026년 11월 20일 15:00까지 이용이 정지되었습니다.');

    final offline = FakeApi({}); // 모든 요청이 연결 오류
    expect(await _loginError(tester, offline), '서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.');
  });
}
