import 'package:go_router/go_router.dart';

import 'auth/auth_service.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';
import 'screens/me_screen.dart';
import 'screens/home_screen.dart';
import 'screens/placeholder_screen.dart';
import 'screens/post_create_screen.dart';
import 'screens/post_detail_screen.dart';
import 'screens/post_edit_screen.dart';
import 'screens/signup_screen.dart';

GoRouter buildRouter(Session session) {
  return GoRouter(
    initialLocation: '/home',
    // 로그아웃·토큰 만료로 session이 바뀌면 redirect를 다시 계산한다.
    refreshListenable: session,
    redirect: (context, state) {
      final location = state.matchedLocation;
      final atAuth = location == '/login' || location == '/signup';
      // 로그인하지 않아도 볼 수 있는 화면: 홈 목록과 글 상세 (웹과 같음). 글쓰기·쪽지·내 정보는 로그인 필요.
      // 수정 화면(/posts/:id/edit)은 로그인이 필요하다.
      final public = location == '/home' || (location.startsWith('/posts/') && !location.endsWith('/edit'));
      if (!session.signedIn) {
        if (atAuth) return null;
        // 로그인이 만료되면 어디에 있든 로그인 화면으로 보낸다(만료 안내를 보여주려고).
        if (session.expired) return '/login';
        return public ? null : '/login';
      }
      return atAuth ? '/home' : null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => LoginScreen(notice: state.extra as String?)),
      GoRoute(path: '/signup', builder: (context, state) => const SignupScreen()),
      GoRoute(
        path: '/posts/:id',
        builder: (context, state) => PostDetailScreen(postId: int.parse(state.pathParameters['id']!)),
      ),
      // 상세 아래가 아닌 따로 둔 경로: 내 글 목록에서 열어도 수정 화면 하나만 쌓이고, 저장하면 연 곳으로 돌아간다.
      GoRoute(
        path: '/posts/:id/edit',
        builder: (context, state) => PostEditScreen(postId: int.parse(state.pathParameters['id']!)),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/home', builder: (context, state) => const HomeScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/sell', builder: (context, state) => const PostCreateScreen()),
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
