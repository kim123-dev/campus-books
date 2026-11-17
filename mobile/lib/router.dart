import 'package:go_router/go_router.dart';

import 'auth/auth_service.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';
import 'screens/me_screen.dart';
import 'screens/placeholder_screen.dart';

GoRouter buildRouter(Session session) {
  return GoRouter(
    initialLocation: '/home',
    // 로그아웃·토큰 만료로 session이 바뀌면 redirect를 다시 계산한다.
    refreshListenable: session,
    redirect: (context, state) {
      final atLogin = state.matchedLocation == '/login';
      if (!session.signedIn) return atLogin ? null : '/login';
      return atLogin ? '/home' : null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/home', builder: (context, state) => const PlaceholderScreen(title: '홈', stage: '교재 목록·검색은 4단계')),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/sell', builder: (context, state) => const PlaceholderScreen(title: '글쓰기', stage: '사진 올리기·글쓰기는 5단계')),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/messages', builder: (context, state) => const PlaceholderScreen(title: '쪽지', stage: '쪽지는 2차 범위')),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/me', builder: (context, state) => const MeScreen()),
          ]),
        ],
      ),
    ],
  );
}
