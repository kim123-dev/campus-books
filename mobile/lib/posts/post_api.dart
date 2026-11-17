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

  /// GET /posts/{id}. 로그인하지 않아도 볼 수 있다.
  Future<PostDetail> detail(int id) async {
    final response = await dio.get<dynamic>('/posts/$id');
    return PostDetail.fromJson(response.data as Map<String, dynamic>);
  }
}
