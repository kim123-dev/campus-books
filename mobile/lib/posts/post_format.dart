// 목록·상세에 쓰는 표기. 웹(static/js/ui.js, i18n/ko.json)의 한국어 표기와 같게 맞춘다.

/// 19900 → "19,900원", 0 → "무료 나눔"
String formatPrice(int price) => price == 0 ? '무료 나눔' : '${formatNumber(price)}원';

String formatNumber(int value) {
  final digits = value.abs().toString();
  final buffer = StringBuffer(value < 0 ? '-' : '');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write(',');
    buffer.write(digits[i]);
  }
  return buffer.toString();
}

const statusLabels = {'ON_SALE': '판매 중', 'RESERVED': '예약 중', 'SOLD': '판매 완료'};
const conditionLabels = {'GOOD': '상', 'FAIR': '중', 'POOR': '하'};

/// 올린 시간: 방금 전 / N분 전 / N시간 전 / N일 전, 일주일이 넘으면 날짜(한국 시간)
String formatPostedAt(DateTime createdAt, {DateTime? now}) {
  final current = (now ?? DateTime.now()).toUtc();
  final diff = current.difference(createdAt.toUtc());
  if (diff.inMinutes < 1) return '방금 전';
  if (diff.inHours < 1) return '${diff.inMinutes}분 전';
  if (diff.inDays < 1) return '${diff.inHours}시간 전';
  if (diff.inDays < 7) return '${diff.inDays}일 전';
  // 기기 시간대와 상관없이 한국 시간(UTC+9)으로 보여준다. 학생들이 모두 한국에 있으므로.
  final kst = createdAt.toUtc().add(const Duration(hours: 9));
  String two(int n) => n.toString().padLeft(2, '0');
  return '${kst.year}.${two(kst.month)}.${two(kst.day)}';
}
