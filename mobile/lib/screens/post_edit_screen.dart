import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../photos/photo_list.dart';
import '../posts/post_actions.dart';
import '../posts/post_events.dart';
import '../posts/post_form.dart';
import '../posts/post_models.dart';
import '../posts/post_rules.dart';
import '../providers.dart';
import '../widgets/state_views.dart';

/// 판매글 수정. 글쓰기 폼을 그대로 쓰고, 지금 내용과 사진을 채워 둔다.
/// 저장은 웹과 같이 PATCH 한 번: 바뀐 글 내용 + 지울 사진 번호(remove_image_ids) + 새로 올린 임시 사진 번호(add_image_ids).
class PostEditScreen extends ConsumerStatefulWidget {
  const PostEditScreen({super.key, required this.postId});

  final int postId;

  @override
  ConsumerState<PostEditScreen> createState() => _PostEditScreenState();
}

class _PostEditScreenState extends ConsumerState<PostEditScreen> {
  PostDetail? _post;
  ApiError? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// 목록에서 본 글이 그 사이 바뀌었을 수 있어 최신 내용을 다시 받는다.
  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final results = await Future.wait<Object?>([
        ref.read(postApiProvider).detail(widget.postId),
        ref.read(authServiceProvider).myId(),
      ]);
      if (!mounted) return;
      final post = results[0] as PostDetail;
      // 아래 두 검사는 수정할 수 없는 글에 폼을 보여주지 않기 위한 것이다. 최종 검사는 저장할 때 서버가 한다.
      if (post.sellerId != results[1]) {
        leaveToList(context, '본인이 작성한 글만 수정할 수 있습니다.');
        return;
      }
      if (post.status == 'SOLD') {
        showMessage(context, '판매 완료된 글은 수정할 수 없습니다.');
        Navigator.of(context).pop();
        return;
      }
      setState(() => _post = post);
    } catch (e) {
      if (!mounted) return;
      final error = ApiError.from(e);
      if (error.status == 404) {
        ref.read(postEventsProvider).emit(PostEvent.deleted(widget.postId));
        leaveToList(context, error.message);
        return;
      }
      setState(() => _error = error);
    }
  }

  Future<void> _save(PostFormResult result) async {
    final body = {
      ...result.values.toJson(),
      // 수정에서는 학교를 비우면 null을 보내야 학교가 풀린다(빼고 보내면 "그대로").
      'school_id': result.values.schoolId,
      'remove_image_ids': result.removedImageIds,
      'add_image_ids': result.pendingImageIds,
    };
    final PostDetail updated;
    try {
      updated = await ref.read(postApiProvider).update(widget.postId, body);
    } on DioException catch (e) {
      final error = ApiError.from(e);
      // 그 사이 지워졌거나(404) 내 글이 아니면(403) 고칠 수 없으니 안내와 함께 목록으로 간다.
      if (mounted && (error.status == 404 || error.status == 403)) {
        if (error.status == 404) ref.read(postEventsProvider).emit(PostEvent.deleted(widget.postId));
        leaveToList(context, error.message);
        return;
      }
      rethrow; // 422·400 등은 폼이 칸·아래 안내에 보여준다.
    }
    ref.read(postEventsProvider).emit(PostEvent.updated(updated));
    if (!mounted) return;
    showMessage(context, '수정했습니다.');
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final post = _post;
    return Scaffold(
      appBar: AppBar(title: const Text('판매글 수정')),
      body: SafeArea(
        child: post != null
            ? PostForm(
                submitLabel: '저장하기',
                initial: initialValuesOf(post),
                existingImages: [
                  for (final image in post.images) ExistingPhoto(id: image.id, thumbnailUrl: image.thumbnailUrl),
                ],
                // 학교를 비워 둔 글은 그대로 둔다(작성할 때와 달리 내 학교를 채우지 않는다).
                preselectMySchool: false,
                resetAfterSubmit: false,
                onSubmit: _save,
              )
            : _error != null
                ? ErrorView(message: _error!.message, onRetry: _load)
                : const LoadingView(),
      ),
    );
  }
}

/// 지금 글 내용을 폼 값으로
PostFormValues initialValuesOf(PostDetail post) => PostFormValues(
      title: post.title,
      bookTitle: post.bookTitle,
      courseName: post.courseName ?? '',
      condition: post.condition,
      price: '${post.price}',
      description: post.description ?? '',
      schoolId: post.schoolId,
    );
