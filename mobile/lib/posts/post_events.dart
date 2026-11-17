import 'package:flutter/foundation.dart';

import 'post_models.dart';

/// 글이 바뀌었다는 알림. 홈 목록·상세·내 글 목록이 듣고 있다가 다시 열지 않아도 바로 반영한다.
class PostEvent {
  const PostEvent.created(this.id) : kind = PostEventKind.created, post = null;
  PostEvent.updated(PostDetail this.post) : kind = PostEventKind.updated, id = post.id;
  const PostEvent.deleted(this.id) : kind = PostEventKind.deleted, post = null;

  final PostEventKind kind;
  final int id;

  /// updated일 때 서버가 돌려준 최신 글
  final PostDetail? post;
}

enum PostEventKind { created, updated, deleted }

/// 마지막 알림 하나만 들고 있는 통로. 알림마다 새 객체라 같은 글을 연달아 바꿔도 매번 알린다.
class PostEvents extends ValueNotifier<PostEvent?> {
  PostEvents() : super(null);

  void emit(PostEvent event) => value = event;
}

/// 목록에 알림을 반영한 결과. 목록에 없던 글이 보여야 하면(새 글 등) null: 새로 받아야 한다.
List<PostSummary>? applyPostEvent(List<PostSummary> items, PostEvent event, {required bool Function(PostSummary) visible}) {
  switch (event.kind) {
    case PostEventKind.created:
      return null;
    case PostEventKind.deleted:
      return [for (final post in items) if (post.id != event.id) post];
    case PostEventKind.updated:
      final updated = event.post!;
      final index = items.indexWhere((post) => post.id == event.id);
      if (index < 0) return visible(updated) ? null : items;
      // 판매 완료로 바뀌어 숨김 조건에 걸리면 목록에서 뺀다.
      if (!visible(updated)) return [...items]..removeAt(index);
      return [...items]..[index] = updated;
  }
}
