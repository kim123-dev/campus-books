import 'package:dio/dio.dart';

/// 서버 오류를 화면에 보여줄 모양으로 바꾼 것. (웹 static/js/api.js의 toApiError와 같은 규칙)
class ApiError {
  const ApiError({this.status, required this.message, this.fieldErrors = const {}, this.retryAfter});

  /// 응답이 없으면(네트워크 오류) null
  final int? status;

  /// 칸에 붙지 않는 오류 문구
  final String message;

  /// 422일 때 칸 이름(email, password, answer …)별 문구
  final Map<String, String> fieldErrors;

  /// 429일 때 다시 시도해도 되는 때까지 남은 초(Retry-After)
  final int? retryAfter;

  bool get isNetwork => status == null;

  static const networkMessage = '서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.';
  static const genericMessage = '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';

  factory ApiError.from(Object error) {
    if (error is! DioException) return const ApiError(message: genericMessage);
    final response = error.response;
    if (response == null) return const ApiError(message: networkMessage);

    final status = response.statusCode;
    final retryAfter = status == 429 ? int.tryParse(response.headers.value('retry-after') ?? '') : null;
    final data = response.data;
    final detail = data is Map ? data['detail'] : null;

    // 400·401·403·409·429: 서버가 보낸 한국어 문구를 그대로 쓴다.
    if (detail is String) return ApiError(status: status, message: detail, retryAfter: retryAfter);

    // 422: [{loc: ["body", "security_question", "answer"], msg, type, ctx, input}, ...]
    if (detail is List) {
      final fields = <String, String>{};
      final general = <String>[];
      for (final item in detail.whereType<Map>()) {
        final loc = (item['loc'] as List?) ?? const [];
        // loc의 마지막 값이 칸 이름이다. ["body"]처럼 칸이 없으면 여러 칸을 함께 본 검사다.
        final field = loc.length > 1 ? '${loc.last}' : null;
        final message = _validationMessage(item);
        if (field == null) {
          general.add(message);
        } else {
          fields.putIfAbsent(field, () => message);
        }
      }
      return ApiError(
        status: status,
        message: general.isEmpty ? '입력값을 확인해 주세요.' : general.join(' '),
        fieldErrors: fields,
      );
    }
    return ApiError(status: status, message: genericMessage, retryAfter: retryAfter);
  }

  /// Pydantic 기본 문구는 영어라 자주 나오는 것만 한국어로 바꾼다. 서버가 직접 만든 문구(ValueError)는 그대로.
  static String _validationMessage(Map item) {
    final ctx = (item['ctx'] as Map?) ?? const {};
    final msg = '${item['msg'] ?? ''}';
    switch (item['type']) {
      case 'missing':
        return '필수 항목입니다.';
      case 'string_too_short':
        return ctx['min_length'] == 1 ? '내용을 입력해 주세요.' : '${ctx['min_length']}자 이상 입력해 주세요.';
      case 'string_too_long':
        return '${ctx['max_length']}자 이하로 입력해 주세요.';
      case 'greater_than_equal':
        return '${ctx['ge']} 이상이어야 합니다.';
      case 'value_error':
        if (msg.startsWith('value is not a valid email address')) return '올바른 이메일 형식이 아닙니다.';
        return msg.replaceFirst(RegExp(r'^Value error, '), '');
      default:
        return '입력값을 확인해 주세요.';
    }
  }
}

/// 로그인 화면용 안내. 429는 Retry-After로 기다릴 시간을, 네트워크 오류는 연결 확인을 알려준다.
String loginErrorMessage(ApiError error) {
  if (error.isNetwork) return ApiError.networkMessage;
  if (error.status == 429) {
    final seconds = error.retryAfter;
    if (seconds == null || seconds <= 0) return '로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.';
    final minutes = (seconds / 60).ceil();
    return '로그인 시도가 너무 많습니다. 잠시 후(약 $minutes분) 다시 시도해 주세요.';
  }
  // 401(불일치), 403(정지: "…까지 이용이 정지되었습니다.")은 서버 문구 그대로
  return error.message;
}
