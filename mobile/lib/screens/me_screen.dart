import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../providers.dart';

/// 내 정보. 2단계에서는 토큰이 붙는지(GET /users/me)와 로그아웃만 확인한다.
class MeScreen extends ConsumerStatefulWidget {
  const MeScreen({super.key});

  @override
  ConsumerState<MeScreen> createState() => _MeScreenState();
}

class _MeScreenState extends ConsumerState<MeScreen> {
  late Future<Map<String, dynamic>> _me = _load();

  Future<Map<String, dynamic>> _load() async {
    final response = await ref.read(dioProvider).get<dynamic>('/users/me');
    return response.data as Map<String, dynamic>;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('내 정보')),
      body: RefreshIndicator(
        onRefresh: () async {
          final next = _load();
          setState(() => _me = next);
          await next.catchError((_) => <String, dynamic>{});
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            FutureBuilder<Map<String, dynamic>>(
              future: _me,
              builder: (context, snapshot) {
                if (snapshot.hasError) return Text(errorMessage(snapshot.error!));
                final me = snapshot.data;
                if (me == null) return const Center(child: CircularProgressIndicator());
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${me['nickname']}', style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text('${me['email']}'),
                  ],
                );
              },
            ),
            const SizedBox(height: 24),
            OutlinedButton(
              onPressed: () => ref.read(authServiceProvider).logout(),
              child: const Text('로그아웃'),
            ),
          ],
        ),
      ),
    );
  }
}
