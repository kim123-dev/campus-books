import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_error.dart';
import '../providers.dart';

/// 로그인(이메일·비밀번호). 성공하면 session이 바뀌고 라우터가 홈으로 보낸다.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key, this.notice});

  /// 다른 화면에서 넘어올 때 위에 보여줄 안내 (예: 가입은 됐지만 자동 로그인 실패)
  final String? notice;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (_email.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = '이메일과 비밀번호를 입력해 주세요.');
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authServiceProvider).login(_email.text, _password.text);
    } catch (e) {
      if (mounted) setState(() => _error = loginErrorMessage(ApiError.from(e)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final expired = ref.watch(sessionProvider).expired;
    final notice = widget.notice ?? (expired ? '로그인이 만료되었습니다. 다시 로그인해 주세요.' : null);
    return Scaffold(
      appBar: AppBar(title: const Text('로그인')),
      // 키보드가 올라오면 화면이 줄고(기본값), 포커스된 칸이 보이도록 ListView가 스크롤된다.
      body: SafeArea(
        child: AutofillGroup(
          child: ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.all(16),
            children: [
              if (notice != null) ...[
                Text(notice),
                const SizedBox(height: 16),
              ],
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                decoration: const InputDecoration(labelText: '학교 이메일'),
                textInputAction: TextInputAction.next,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _password,
                obscureText: true,
                autofillHints: const [AutofillHints.password],
                decoration: const InputDecoration(labelText: '비밀번호'),
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  key: const Key('login-error'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? '로그인 중…' : '로그인'),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: _busy ? null : () => context.go('/signup'),
                child: const Text('처음이신가요? 회원가입'),
              ),
              // 웹처럼 글 목록과 상세는 로그인 없이 볼 수 있다.
              TextButton(
                onPressed: _busy
                    ? null
                    : () {
                        ref.read(sessionProvider).clearExpired();
                        context.go('/home');
                      },
                child: const Text('로그인 없이 둘러보기'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
