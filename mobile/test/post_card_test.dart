import 'package:campus_books/posts/post_card.dart';
import 'package:campus_books/posts/post_format.dart';
import 'package:campus_books/posts/post_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('가격은 천 단위 쉼표와 원, 0원은 무료 나눔 (웹과 같은 표기)', () {
    expect(formatPrice(0), '무료 나눔');
    expect(formatPrice(500), '500원');
    expect(formatPrice(1000), '1,000원');
    expect(formatPrice(19900), '19,900원');
    expect(formatPrice(1234567), '1,234,567원');
  });

  test('올린 시간과 서버 시간 해석(시간대 없는 값은 UTC)', () {
    final now = DateTime.utc(2026, 11, 17, 12);
    expect(formatPostedAt(now.subtract(const Duration(seconds: 30)), now: now), '방금 전');
    expect(formatPostedAt(now.subtract(const Duration(minutes: 5)), now: now), '5분 전');
    expect(formatPostedAt(now.subtract(const Duration(hours: 3)), now: now), '3시간 전');
    expect(formatPostedAt(now.subtract(const Duration(days: 2)), now: now), '2일 전');
    // 11월 1일 20:00 UTC = 11월 2일 05:00 한국 시간
    expect(formatPostedAt(DateTime.utc(2026, 11, 1, 20), now: now), '2026.11.02');
    expect(parseServerTime('2026-11-16T11:32:27.402772'), DateTime.utc(2026, 11, 16, 11, 32, 27, 402, 772));
    expect(parseServerTime('2026-11-16T11:32:27Z'), DateTime.utc(2026, 11, 16, 11, 32, 27));
  });

  testWidgets('카드에 제목·가격·판매 상태·올린 시간이 보인다', (tester) async {
    final post = PostSummary(
      id: 1,
      title: '자료구조 팝니다',
      bookTitle: '자료구조',
      courseName: null,
      condition: 'GOOD',
      price: 19900,
      status: 'RESERVED',
      sellerId: 1,
      sellerNickname: '판매자',
      thumbnailUrl: null,
      schoolName: null,
      createdAt: DateTime.utc(2026, 11, 17, 11),
    );
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PostCard(post: post, imageBase: 'http://test', onTap: () {}, now: DateTime.utc(2026, 11, 17, 12)),
      ),
    ));
    expect(find.text('자료구조 팝니다'), findsOneWidget);
    expect(find.text('19,900원'), findsOneWidget);
    expect(find.text('예약 중'), findsOneWidget);
    expect(find.text('1시간 전'), findsOneWidget);
  });
}
