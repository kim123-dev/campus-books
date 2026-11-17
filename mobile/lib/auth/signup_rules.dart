import 'dart:convert';

import 'package:unorm_dart/unorm_dart.dart' as unorm;

/// 가입 입력 규칙. 서버(app/schemas/user.py, security_question.py)·웹(signup.js, security-question.js)과 같은 값.
/// 여기서는 보내기 전에 빠르게 알려주는 용도이고, 최종 검사는 서버가 한다(서버 문구가 오면 그대로 보여준다).
const passwordMin = 8;
const passwordMax = 64;
const passwordMaxBytes = 72; // bcrypt 한도. 한글은 한 글자가 3바이트라 64자 안에서도 넘을 수 있다.
const nicknameMin = 2;
const nicknameMax = 30;
const customQuestionMin = 5;
const customQuestionMax = 60;
const answerMin = 2;
const answerMax = 20;
const answerRawMax = 100;

/// 질문 선택값 중 "직접 만들기"
const customQuestionKey = '__custom';

/// 서버 normalize_answer와 같다: NFKC, 소문자, 모든 공백 제거.
String normalizeAnswer(String value) =>
    unorm.nfkc(value).toLowerCase().replaceAll(RegExp(r'\s+', unicode: true), '');

class SignupInput {
  const SignupInput({
    required this.email,
    required this.password,
    required this.passwordConfirm,
    required this.nickname,
    required this.questionKey,
    required this.customQuestion,
    required this.answer,
    this.schoolId,
  });

  final String email;
  final String password;
  final String passwordConfirm;
  final String nickname;

  /// 고른 질문 key. 직접 만들기면 [customQuestionKey], 안 골랐으면 null.
  final String? questionKey;
  final String customQuestion;
  final String answer;
  final int? schoolId;

  /// POST /auth/signup 본문. 학교를 안 골랐으면 school_id를 보내지 않는다(웹과 같음).
  Map<String, dynamic> toJson() => {
        'email': email.trim(),
        'password': password,
        'nickname': nickname,
        'security_question': questionKey == customQuestionKey
            ? {'custom_question': customQuestion.trim(), 'answer': answer}
            : {'question_key': questionKey, 'answer': answer},
        if (schoolId != null) 'school_id': schoolId,
      };
}

final _email = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$');

/// 칸 이름(서버 422의 칸 이름과 같게)별 오류. 문제가 없으면 빈 맵.
Map<String, String> validateSignup(SignupInput input, {String? questionText}) {
  final errors = <String, String>{};

  final email = input.email.trim();
  if (email.isEmpty) {
    errors['email'] = '필수 항목입니다.';
  } else if (!_email.hasMatch(email)) {
    errors['email'] = '올바른 이메일 형식이 아닙니다.';
  }

  final password = input.password;
  if (password.length < passwordMin) {
    errors['password'] = '$passwordMin자 이상 입력해 주세요.';
  } else if (password.length > passwordMax) {
    errors['password'] = '$passwordMax자 이하로 입력해 주세요.';
  } else if (utf8.encode(password).length > passwordMaxBytes) {
    errors['password'] = '비밀번호는 $passwordMaxBytes바이트 이하여야 합니다.';
  }
  // 비밀번호 확인은 서버 API에 없는 칸이라 앱에서만 본다.
  if (input.passwordConfirm != password) errors['password_confirm'] = '비밀번호가 일치하지 않습니다.';

  final nickname = input.nickname.trim();
  if (nickname.length < nicknameMin) {
    errors['nickname'] = '$nicknameMin자 이상 입력해 주세요.';
  } else if (nickname.length > nicknameMax) {
    errors['nickname'] = '$nicknameMax자 이하로 입력해 주세요.';
  }

  if (input.questionKey == null) {
    errors['question_key'] = '질문을 골라 주세요.';
  } else if (input.questionKey == customQuestionKey) {
    final custom = input.customQuestion.trim();
    if (custom.length < customQuestionMin) {
      errors['custom_question'] = '질문을 $customQuestionMin자 이상 적어 주세요.';
    } else if (custom.length > customQuestionMax) {
      errors['custom_question'] = '$customQuestionMax자 이하로 입력해 주세요.';
    }
  }

  final answer = normalizeAnswer(input.answer);
  if (input.answer.length > answerRawMax) {
    errors['answer'] = '$answerRawMax자 이하로 입력해 주세요.';
  } else if (answer.length < answerMin) {
    errors['answer'] = '답은 공백을 빼고 $answerMin자 이상이어야 합니다.';
  } else if (answer.length > answerMax) {
    errors['answer'] = '답은 공백을 빼고 $answerMax자 이하여야 합니다.';
  } else {
    // 질문만 보고 답을 알 수 있으면 안 된다(서버와 같은 검사).
    final question = input.questionKey == customQuestionKey ? input.customQuestion.trim() : questionText;
    if (question != null && question.isNotEmpty && normalizeAnswer(question).contains(answer)) {
      errors['answer'] = '답이 질문 안에 그대로 들어 있어요. 질문만 보고 알 수 없는 답으로 정해 주세요.';
    }
  }
  return errors;
}
