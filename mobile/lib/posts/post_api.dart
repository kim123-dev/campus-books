import 'package:dio/dio.dart';

import 'post_models.dart';

/// 목록 한 번에 받는 글 수. 서버 한도(MAX_PAGE_SIZE=100) 안에서 한 화면 반쯤 더 여유 있게.
const postPageSize = 20;

class PostQuery {
  const PostQuery({this.q = '', this.includeSold = false});

  final String q;

  /// 판매 완료 글도 볼지. 기본은 숨김(웹 홈과 같음).
  final bool includeSold;

  PostQuery copyWith({String? q, bool? includeSold}) =>
      PostQuery(q: q ?? this.q, includeSold: includeSold ?? this.includeSold);
}

class PostApi {
  PostApi(this.dio);

  final Dio dio;

  /// GET /posts. 로그인하지 않아도 볼 수 있다(토큰이 있으면 인터셉터가 붙인다).
  Future<PostPage> list(PostQuery query, int page) async {
    final response = await dio.get<dynamic>('/posts', queryParameters: {
      if (query.q.trim().isNotEmpty) 'q': query.q.trim(),
      'include_sold': query.includeSold,
      'page': page,
      'size': postPageSize,
    });
    return PostPage.fromJson(response.data as Map<String, dynamic>);
  }

  /// POST /posts. 만든 글 번호를 돌려준다.
  Future<int> create(Map<String, dynamic> body) async {
    final response = await dio.post<dynamic>('/posts', data: body);
    return (response.data as Map)['id'] as int;
  }

  /// 내 학교 번호(없으면 null). 글쓰기에서 학교를 미리 고르는 데 쓴다.
  Future<int?> mySchool() async {
    final response = await dio.get<dynamic>('/users/me/school');
    final school = (response.data as Map)['school'] as Map?;
    return school?['id'] as int?;
  }

  /// GET /posts/{id}. 로그인하지 않아도 볼 수 있다.
  Future<PostDetail> detail(int id) async {
    final response = await dio.get<dynamic>('/posts/$id');
    return PostDetail.fromJson(response.data as Map<String, dynamic>);
  }

  /// GET /users/me/posts 전부(최신순). 상태별로 나눠 보여주려면 다 받아야 해서 한도(100)씩 끝까지 받는다.
  Future<List<PostSummary>> myPosts() async {
    final items = <PostSummary>[];
    final seen = <int>{};
    // 내 글은 많아야 수십 개라 보통 한 번에 끝난다. 혹시 모를 무한 반복만 막는다.
    for (var page = 1; page <= 20; page++) {
      final response = await dio.get<dynamic>('/users/me/posts', queryParameters: {'page': page, 'size': 100});
      final result = PostPage.fromJson(response.data as Map<String, dynamic>);
      items.addAll(result.items.where((post) => seen.add(post.id)));
      if (result.items.isEmpty || items.length >= result.total) break;
    }
    return items;
  }

  /// PATCH /posts/{id}. 보낸 칸만 바뀐다(사진은 remove_image_ids·add_image_ids).
  Future<PostDetail> update(int id, Map<String, dynamic> body) async {
    final response = await dio.patch<dynamic>('/posts/$id', data: body);
    return PostDetail.fromJson(response.data as Map<String, dynamic>);
  }

  /// PATCH /posts/{id}/status. 판매 완료일 때만 거래한 사람(buyerId)을 함께 보낼 수 있다.
  Future<PostDetail> changeStatus(int id, String status, {int? buyerId}) async {
    final response = await dio.patch<dynamic>('/posts/$id/status', data: {
      'status': status,
      'buyer_id': ?buyerId,
    });
    return PostDetail.fromJson(response.data as Map<String, dynamic>);
  }

  /// GET /posts/{id}/buyer의 후보(이 글로 쪽지를 주고받은 사람). 판매 완료 창에서 고른다.
  Future<List<BuyerCandidate>> buyerCandidates(int id) async {
    final response = await dio.get<dynamic>('/posts/$id/buyer');
    return [
      for (final c in ((response.data as Map)['candidates'] as List).cast<Map<String, dynamic>>())
        BuyerCandidate(id: c['id'] as int, nickname: c['nickname'] as String),
    ];
  }

  /// DELETE /posts/{id}
  Future<void> delete(int id) => dio.delete<dynamic>('/posts/$id');
}
