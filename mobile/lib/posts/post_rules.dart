import 'post_format.dart';

/// 판매글 입력 규칙. 서버(app/schemas/post.py의 PostCreate·PostUpdate)·웹(post-form.html)과 같은 값.
/// 보내기 전에 빠르게 알려주는 용도이고, 최종 검사는 서버가 한다(서버 문구가 오면 그대로 보여준다).
const titleMax = 100;
const bookTitleMax = 200;
const courseNameMax = 100;
const descriptionMax = 2000;
const maxPrice = 10000000;
const maxPhotos = 3;

/// 글쓰기·수정 폼에 적은 값
class PostFormValues {
  const PostFormValues({
    this.title = '',
    this.bookTitle = '',
    this.courseName = '',
    this.condition,
    this.price = '',
    this.description = '',
    this.schoolId,
  });

  final String title;
  final String bookTitle;
  final String courseName;

  /// GOOD / FAIR / POOR. 안 골랐으면 null.
  final String? condition;

  /// 입력칸 그대로(숫자만 입력되게 막아 둔다)
  final String price;
  final String description;
  final int? schoolId;

  /// POST /posts 본문(사진 번호 제외). 서버처럼 앞뒤 공백은 빼고, 빈 선택 항목은 보내지 않는다(null).
  Map<String, dynamic> toJson() => {
        'title': title.trim(),
        'book_title': bookTitle.trim(),
        'course_name': courseName.trim().isEmpty ? null : courseName.trim(),
        'condition': condition,
        'price': int.parse(price.trim()),
        'description': description.trim().isEmpty ? null : description,
        if (schoolId != null) 'school_id': schoolId,
      };
}

/// 칸 이름(서버 422의 칸 이름과 같게)별 오류. 문제가 없으면 빈 맵.
/// 글자 수는 서버(파이썬)와 같게 유니코드 문자 단위로 센다(이모지 하나 = 1자).
Map<String, String> validatePost(PostFormValues v) {
  final errors = <String, String>{};
  int chars(String s) => s.runes.length;

  final title = v.title.trim();
  if (title.isEmpty) {
    errors['title'] = '내용을 입력해 주세요.';
  } else if (chars(title) > titleMax) {
    errors['title'] = '$titleMax자 이하로 입력해 주세요.';
  }

  final bookTitle = v.bookTitle.trim();
  if (bookTitle.isEmpty) {
    errors['book_title'] = '내용을 입력해 주세요.';
  } else if (chars(bookTitle) > bookTitleMax) {
    errors['book_title'] = '$bookTitleMax자 이하로 입력해 주세요.';
  }

  if (chars(v.courseName.trim()) > courseNameMax) errors['course_name'] = '$courseNameMax자 이하로 입력해 주세요.';

  if (v.condition == null) errors['condition'] = '필수 항목입니다.';

  final price = v.price.trim();
  final parsed = int.tryParse(price);
  if (price.isEmpty) {
    errors['price'] = '필수 항목입니다.';
  } else if (parsed == null) {
    errors['price'] = '정수로 입력해 주세요.';
  } else if (parsed < 0) {
    errors['price'] = '0 이상이어야 합니다.';
  } else if (parsed > maxPrice) {
    errors['price'] = '${formatNumber(maxPrice)} 이하여야 합니다.';
  }

  if (chars(v.description) > descriptionMax) errors['description'] = '$descriptionMax자 이하로 입력해 주세요.';
  return errors;
}
