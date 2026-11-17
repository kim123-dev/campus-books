import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_error.dart';
import '../auth/auth_service.dart';
import '../auth/signup_rules.dart';
import '../providers.dart';

/// 회원가입: 이메일·비밀번호·닉네임, 학교(선택), 본인 확인 질문과 답.
/// 가입이 성공하면 바로 로그인되고 라우터가 홈으로 보낸다.
class SignupScreen extends ConsumerStatefulWidget {
  const SignupScreen({super.key});

  @override
  ConsumerState<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends ConsumerState<SignupScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _passwordConfirm = TextEditingController();
  final _nickname = TextEditingController();
  final _customQuestion = TextEditingController();
  final _answer = TextEditingController();

  List<School> _schools = const [];
  int? _schoolId;
  List<SecurityQuestion>? _questions;
  bool _questionsFailed = false;
  String? _questionKey;

  Map<String, String> _errors = const {};
  String? _generalError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadSchools();
    _loadQuestions();
  }

  @override
  void dispose() {
    for (final c in [_email, _password, _passwordConfirm, _nickname, _customQuestion, _answer]) {
      c.dispose();
    }
    super.dispose();
  }

  /// 학교는 선택 항목이라 목록을 못 받아도 가입할 수 있다. 하나뿐이면 미리 고른다(웹과 같음).
  Future<void> _loadSchools() async {
    try {
      final schools = await ref.read(authServiceProvider).schools();
      if (!mounted) return;
      setState(() {
        _schools = schools;
        if (schools.length == 1) _schoolId = schools.single.id;
      });
    } catch (_) {}
  }

  Future<void> _loadQuestions() async {
    setState(() => _questionsFailed = false);
    try {
      final questions = await ref.read(authServiceProvider).securityQuestions();
      if (mounted) setState(() => _questions = questions);
    } catch (_) {
      // 직접 만든 질문으로는 가입할 수 있으니 다시 불러오기 버튼만 보여준다.
      if (mounted) setState(() => _questionsFailed = true);
    }
  }

  SignupInput get _input => SignupInput(
        email: _email.text,
        password: _password.text,
        passwordConfirm: _passwordConfirm.text,
        nickname: _nickname.text,
        questionKey: _questionKey,
        customQuestion: _customQuestion.text,
        answer: _answer.text,
        schoolId: _schoolId,
      );

  String? get _questionText {
    for (final q in _questions ?? const <SecurityQuestion>[]) {
      if (q.key == _questionKey) return q.text;
    }
    return null;
  }

  Future<void> _submit() async {
    if (_busy) return;
    final input = _input;
    final errors = validateSignup(input, questionText: _questionText);
    setState(() {
      _errors = errors;
      _generalError = errors.isEmpty ? null : '입력값을 확인해 주세요.';
    });
    if (errors.isNotEmpty) return;

    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    try {
      await ref.read(authServiceProvider).signup(input);
      // 성공: session이 바뀌어 라우터가 홈으로 보낸다.
    } on SignedUpButLoginFailed catch (e) {
      if (mounted) {
        context.go('/login', extra: '가입되었습니다. ${loginErrorMessage(ApiError.from(e.cause))}');
      }
    } catch (e) {
      final error = ApiError.from(e);
      if (mounted) {
        setState(() {
          _errors = error.fieldErrors;
          // 409(이메일·닉네임 중복) 등 서버 문구는 그대로 보여준다.
          _generalError = error.message;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final errorColor = Theme.of(context).colorScheme.error;
    final custom = _questionKey == customQuestionKey;
    return Scaffold(
      appBar: AppBar(
        title: const Text('회원가입'),
        leading: BackButton(onPressed: () => context.go('/login')),
      ),
      body: SafeArea(
        child: AutofillGroup(
          // 키보드가 올라오면 화면이 줄고, 포커스된 칸이 보이도록 스크롤된다.
          child: ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              _field(
                name: 'email',
                controller: _email,
                label: '학교 이메일',
                keyboardType: TextInputType.emailAddress,
                autofill: AutofillHints.email,
              ),
              _field(
                name: 'password',
                controller: _password,
                label: '비밀번호',
                helper: '$passwordMin~$passwordMax자',
                obscure: true,
                autofill: AutofillHints.newPassword,
              ),
              _field(
                name: 'password_confirm',
                controller: _passwordConfirm,
                label: '비밀번호 확인',
                obscure: true,
                autofill: AutofillHints.newPassword,
              ),
              _field(
                name: 'nickname',
                controller: _nickname,
                label: '닉네임',
                helper: '$nicknameMin~$nicknameMax자, 다른 학생에게 판매자 이름으로 보입니다.',
                autofill: AutofillHints.nickname,
              ),
              DropdownButtonFormField<int?>(
                key: const Key('school'),
                initialValue: _schoolId,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: '학교 (선택)',
                  helperText: '같은 학교 글을 모아 볼 수 있어요. 내 정보에서 바꿀 수 있어요.',
                  helperMaxLines: 2,
                  errorText: _errors['school_id'],
                ),
                items: [
                  const DropdownMenuItem<int?>(value: null, child: Text('선택 안 함')),
                  for (final s in _schools) DropdownMenuItem<int?>(value: s.id, child: Text(s.name)),
                ],
                onChanged: _busy ? null : (value) => setState(() => _schoolId = value),
              ),
              const SizedBox(height: 24),
              Text('비밀번호를 잊었을 때', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text('비밀번호를 잊었을 때 이 질문의 답으로 재설정해요.'),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                key: const Key('question'),
                initialValue: _questionKey,
                isExpanded: true,
                hint: const Text('질문을 골라 주세요'),
                decoration: InputDecoration(labelText: '질문', errorText: _errors['question_key']),
                items: [
                  for (final q in _questions ?? const <SecurityQuestion>[])
                    DropdownMenuItem(value: q.key, child: Text(q.text, maxLines: 2, overflow: TextOverflow.ellipsis)),
                  const DropdownMenuItem(value: customQuestionKey, child: Text('직접 만들기')),
                ],
                onChanged: _busy ? null : (value) => setState(() => _questionKey = value),
              ),
              if (_questionsFailed)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(onPressed: _loadQuestions, child: const Text('질문 목록 다시 불러오기')),
                ),
              const SizedBox(height: 12),
              if (custom)
                _field(
                  name: 'custom_question',
                  controller: _customQuestion,
                  label: '내가 만든 질문',
                  helper: '$customQuestionMin~$customQuestionMax자. 질문에 답이나 답의 힌트를 넣지 마세요.',
                  maxLength: customQuestionMax,
                ),
              _field(
                name: 'answer',
                controller: _answer,
                label: '답',
                helper: '남이 쉽게 알 수 없는 답으로 정해 주세요. 띄어쓰기와 대소문자는 구분하지 않아요. (공백 빼고 $answerMin~$answerMax자)',
                // 질문과 답을 함께 본 서버 검사(답이 질문에 들어 있음)는 이 칸에 보여준다.
                extraError: _errors['security_question'],
                maxLength: answerRawMax,
                done: true,
              ),
              if (_generalError != null) ...[
                const SizedBox(height: 4),
                Text(_generalError!, key: const Key('signup-error'), style: TextStyle(color: errorColor)),
              ],
              const SizedBox(height: 16),
              FilledButton(
                key: const Key('signup-submit'),
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? '가입 중…' : '가입하기'),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: _busy ? null : () => context.go('/login'),
                child: const Text('이미 회원이신가요? 로그인'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _field({
    required String name,
    required TextEditingController controller,
    required String label,
    String? helper,
    bool obscure = false,
    TextInputType? keyboardType,
    String? autofill,
    String? extraError,
    int? maxLength,
    bool done = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        key: Key(name),
        controller: controller,
        obscureText: obscure,
        keyboardType: keyboardType,
        maxLength: maxLength,
        autofillHints: autofill == null ? null : [autofill],
        textInputAction: done ? TextInputAction.done : TextInputAction.next,
        onSubmitted: done ? (_) => _submit() : null,
        decoration: InputDecoration(
          labelText: label,
          helperText: helper,
          helperMaxLines: 3,
          errorText: _errors[name] ?? extraError,
          errorMaxLines: 3,
          // 글자 수 표시는 숨긴다(길이 한도는 넘치지 않게 막는 용도).
          counterText: '',
        ),
      ),
    );
  }
}
