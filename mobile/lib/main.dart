import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'api/token_storage.dart';
import 'auth/auth_service.dart';
import 'providers.dart';
import 'router.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 저장된 토큰이 있으면 바로 홈으로. 만료됐더라도 첫 요청에서 인터셉터가 갱신한다.
  final storage = SecureTokenStorage();
  final session = Session(signedIn: await storage.read() != null);
  runApp(ProviderScope(
    overrides: [
      tokenStorageProvider.overrideWithValue(storage),
      sessionProvider.overrideWithValue(session),
    ],
    child: CampusBooksApp(router: buildRouter(session)),
  ));
}

class CampusBooksApp extends StatelessWidget {
  const CampusBooksApp({super.key, required this.router});

  final GoRouter router;

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Campus Books',
      theme: buildTheme(),
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
