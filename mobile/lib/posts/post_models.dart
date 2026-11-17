/// 판매글 목록·상세 응답 (app/schemas/post.py의 PostResponse, PostDetailResponse)
class PostSummary {
  const PostSummary({
    required this.id,
    required this.title,
    required this.bookTitle,
    required this.courseName,
    required this.condition,
    required this.price,
    required this.status,
    required this.sellerId,
    required this.sellerNickname,
    required this.thumbnailUrl,
    required this.schoolName,
    required this.createdAt,
  });

  final int id;
  final String title;
  final String bookTitle;
  final String? courseName;
  final String condition;
  final int price;
  final String status;
  final int sellerId;
  final String sellerNickname;

  /// "/images/…" 같은 서버 기준 경로. 사진이 없으면 null.
  final String? thumbnailUrl;
  final String? schoolName;
  final DateTime createdAt;

  factory PostSummary.fromJson(Map<String, dynamic> json) {
    final seller = json['seller'] as Map<String, dynamic>;
    final school = json['school'] as Map<String, dynamic>?;
    return PostSummary(
      id: json['id'] as int,
      title: json['title'] as String,
      bookTitle: json['book_title'] as String,
      courseName: json['course_name'] as String?,
      condition: json['condition'] as String,
      price: json['price'] as int,
      status: json['status'] as String,
      sellerId: seller['id'] as int,
      sellerNickname: seller['nickname'] as String,
      thumbnailUrl: json['thumbnail_url'] as String?,
      schoolName: school?['name'] as String?,
      createdAt: parseServerTime(json['created_at'] as String),
    );
  }
}

class PostImage {
  const PostImage({required this.url, required this.thumbnailUrl});

  final String url;
  final String thumbnailUrl;
}

class PostDetail extends PostSummary {
  const PostDetail({
    required super.id,
    required super.title,
    required super.bookTitle,
    required super.courseName,
    required super.condition,
    required super.price,
    required super.status,
    required super.sellerId,
    required super.sellerNickname,
    required super.thumbnailUrl,
    required super.schoolName,
    required super.createdAt,
    required this.description,
    required this.images,
  });

  final String? description;
  final List<PostImage> images;

  factory PostDetail.fromJson(Map<String, dynamic> json) {
    final s = PostSummary.fromJson(json);
    return PostDetail(
      id: s.id,
      title: s.title,
      bookTitle: s.bookTitle,
      courseName: s.courseName,
      condition: s.condition,
      price: s.price,
      status: s.status,
      sellerId: s.sellerId,
      sellerNickname: s.sellerNickname,
      thumbnailUrl: s.thumbnailUrl,
      schoolName: s.schoolName,
      createdAt: s.createdAt,
      description: json['description'] as String?,
      images: [
        for (final image in (json['images'] as List? ?? const []).cast<Map<String, dynamic>>())
          PostImage(url: image['url'] as String, thumbnailUrl: image['thumbnail_url'] as String),
      ],
    );
  }
}

class PostPage {
  const PostPage({required this.items, required this.total, required this.page});

  final List<PostSummary> items;
  final int total;
  final int page;

  factory PostPage.fromJson(Map<String, dynamic> json) => PostPage(
        items: [for (final item in (json['items'] as List).cast<Map<String, dynamic>>()) PostSummary.fromJson(item)],
        total: json['total'] as int,
        page: json['page'] as int,
      );
}

/// 서버 시간은 UTC다. SQLite(개발)는 시간대 표시 없이 오므로 그때도 UTC로 본다. (웹 parseServerDate와 같음)
DateTime parseServerTime(String text) {
  final hasZone = RegExp(r'(Z|[+-]\d{2}:?\d{2})$').hasMatch(text);
  return DateTime.parse(hasZone ? text : '${text}Z');
}
