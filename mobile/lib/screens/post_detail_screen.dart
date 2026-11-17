import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_error.dart';
import '../posts/post_actions.dart';
import '../posts/post_card.dart';
import '../posts/post_events.dart';
import '../posts/post_format.dart';
import '../posts/post_models.dart';
import '../providers.dart';
import '../widgets/state_views.dart';
import 'photo_viewer_screen.dart';

/// 판매글 상세. 로그인하지 않아도 볼 수 있다(웹과 같음). 쪽지·찜은 2차 범위라 "준비 중".
/// 내 글이면 수정·판매 상태 변경·삭제를 바로 할 수 있다.
class PostDetailScreen extends ConsumerStatefulWidget {
  const PostDetailScreen({super.key, required this.postId});

  final int postId;

  @override
  ConsumerState<PostDetailScreen> createState() => _PostDetailScreenState();
}

class _PostDetailScreenState extends ConsumerState<PostDetailScreen> {
  PostDetail? _post;
  int? _myId;
  ApiError? _error;
  bool _loading = true;
  int _photoIndex = 0;
  // 상태 변경·삭제 중(버튼을 두 번 누르지 않게)
  bool _busy = false;
  late final PostEvents _events;

  @override
  void initState() {
    super.initState();
    _load();
    // 수정 화면이나 내 글 목록에서 바꾼 내용을 다시 열지 않아도 보여준다.
    _events = ref.read(postEventsProvider)..addListener(_onPostEvent);
  }

  @override
  void dispose() {
    _events.removeListener(_onPostEvent);
    super.dispose();
  }

  void _onPostEvent() {
    final event = _events.value;
    if (event == null || event.id != widget.postId || event.kind != PostEventKind.updated) return;
    setState(() {
      _post = event.post;
      // 사진이 바뀌었을 수 있어 첫 장부터 다시 보여준다(사진 줄은 사진 번호를 key로 새로 만든다).
      _photoIndex = 0;
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait<Object?>([
        ref.read(postApiProvider).detail(widget.postId),
        // 내 글인지 알려고. 로그인하지 않았으면 null.
        ref.read(authServiceProvider).myId(),
      ]);
      if (!mounted) return;
      setState(() {
        _post = results[0] as PostDetail;
        _myId = results[1] as int?;
      });
    } catch (e) {
      if (!mounted) return;
      final error = ApiError.from(e);
      setState(() => _error = error);
      // 이미 지워진 글이면 목록에 남아 있지 않게 알린다.
      if (error.status == 404) ref.read(postEventsProvider).emit(PostEvent.deleted(widget.postId));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _comingSoon(String what) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('$what 기능은 준비 중입니다.')));
  }

  @override
  Widget build(BuildContext context) {
    final post = _post;
    return Scaffold(
      appBar: AppBar(title: const Text('판매글')),
      body: post != null
          ? RefreshIndicator(onRefresh: _load, child: _content(post))
          : _loading
              ? const LoadingView()
              : _error?.status == 404
                  ? MessageView(
                      icon: Icons.search_off,
                      title: '글을 찾을 수 없습니다',
                      body: _error!.message,
                      action: FilledButton(
                        onPressed: () => Navigator.of(context).popUntil((route) => route.isFirst),
                        child: const Text('목록으로'),
                      ),
                    )
                  : ErrorView(message: _error?.message ?? '', onRetry: _load),
      bottomNavigationBar: post == null ? null : _actions(post),
    );
  }

  Widget _content(PostDetail post) {
    final theme = Theme.of(context);
    final imageBase = ref.watch(dioProvider).options.baseUrl;
    final info = <(String, String)>[
      ('교재명', post.bookTitle),
      if (post.courseName != null) ('과목', post.courseName!),
      ('책 상태', conditionLabels[post.condition] ?? post.condition),
      if (post.schoolName != null) ('학교', post.schoolName!),
      ('올린 시간', formatPostedAt(post.createdAt)),
    ];
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        _photos(post, imageBase),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.person_outline, size: 20),
                  const SizedBox(width: 6),
                  Expanded(child: Text(post.sellerNickname, style: theme.textTheme.titleSmall)),
                ],
              ),
              const Divider(height: 24),
              StatusBadge(status: post.status),
              const SizedBox(height: 8),
              Text(post.title, style: theme.textTheme.titleLarge),
              const SizedBox(height: 4),
              Text(formatPrice(post.price), style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 16),
              for (final (label, value) in info)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 72,
                        child: Text(label, style: TextStyle(color: theme.colorScheme.outline)),
                      ),
                      Expanded(child: Text(value)),
                    ],
                  ),
                ),
              if ((post.description ?? '').trim().isNotEmpty) ...[
                const Divider(height: 24),
                Text(post.description!, style: theme.textTheme.bodyLarge),
              ],
            ],
          ),
        ),
      ],
    );
  }

  /// 사진: 좌우로 넘기고, 누르면 전체 화면에서 확대
  Widget _photos(PostDetail post, String imageBase) {
    if (post.images.isEmpty) {
      return AspectRatio(
        aspectRatio: 4 / 3,
        child: ColoredBox(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          child: const Center(child: Text('사진이 없습니다')),
        ),
      );
    }
    final urls = [for (final image in post.images) '$imageBase${image.url}'];
    return AspectRatio(
      aspectRatio: 1,
      child: Stack(
        children: [
          PageView.builder(
            key: ValueKey(post.images.map((image) => image.id).join(',')),
            itemCount: urls.length,
            onPageChanged: (index) => setState(() => _photoIndex = index),
            itemBuilder: (context, index) => GestureDetector(
              onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                fullscreenDialog: true,
                builder: (_) => PhotoViewerScreen(urls: urls, initialIndex: index),
              )),
              child: Semantics(
                label: '사진 ${index + 1}/${urls.length}, 눌러서 크게 보기',
                child: CachedNetworkImage(
                  imageUrl: urls[index],
                  fit: BoxFit.cover,
                  placeholder: (_, _) => const ColoredBox(color: Colors.black12),
                  errorWidget: (_, _, _) => const Center(child: Icon(Icons.broken_image_outlined)),
                ),
              ),
            ),
          ),
          if (urls.length > 1)
            Positioned(
              right: 12,
              bottom: 12,
              child: DecoratedBox(
                decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(12)),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  child: Text('${_photoIndex + 1} / ${urls.length}', style: const TextStyle(color: Colors.white)),
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// 내 글: 수정(판매 완료면 숨기고 안내), 판매 상태 변경, 삭제
  Widget _ownerActions(PostDetail post) {
    final sold = post.status == 'SOLD';
    final theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (sold)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(soldNotice, style: theme.textTheme.bodySmall),
          ),
        Row(
          children: [
            if (!sold) ...[
              Expanded(
                child: OutlinedButton.icon(
                  key: const Key('edit-post'),
                  onPressed: _busy ? null : () => context.push('/posts/${post.id}/edit'),
                  icon: const Icon(Icons.edit_outlined),
                  label: const Text('수정'),
                ),
              ),
              const SizedBox(width: 8),
            ],
            Expanded(
              child: FilledButton.tonalIcon(
                key: const Key('change-status'),
                // 판매 완료는 되돌리기 하나뿐이라 고르는 창 없이 바로 확인 창으로 간다.
                onPressed: _busy
                    ? null
                    : () => _run(() => sold ? changePostStatus(context, ref, post, 'ON_SALE') : chooseStatus(context, ref, post)),
                icon: const Icon(Icons.swap_horiz),
                label: Text(sold ? '판매 중으로 되돌리기' : '상태 변경'),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              key: const Key('delete-post'),
              tooltip: '삭제',
              color: theme.colorScheme.error,
              onPressed: _busy ? null : () => _run(() => deletePost(context, ref, post.id)),
              icon: const Icon(Icons.delete_outline),
            ),
          ],
        ),
      ],
    );
  }

  /// 아래 버튼: 내 글이면 관리 버튼, 로그인 안 했으면 로그인 안내(웹과 같음), 아니면 찜·쪽지(준비 중)
  Widget _actions(PostDetail post) {
    final signedIn = ref.read(sessionProvider).signedIn;
    final Widget row;
    if (_myId != null && _myId == post.sellerId) {
      row = _ownerActions(post);
    } else if (!signedIn) {
      row = FilledButton(onPressed: () => context.go('/login'), child: const Text('로그인하고 문의하기'));
    } else {
      row = Row(
        children: [
          OutlinedButton.icon(
            onPressed: () => _comingSoon('찜'),
            icon: const Icon(Icons.favorite_border),
            label: const Text('찜'),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: FilledButton.icon(
              onPressed: () => _comingSoon('쪽지'),
              icon: const Icon(Icons.mail_outline),
              label: const Text('쪽지 보내기'),
            ),
          ),
        ],
      );
    }
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
        child: SizedBox(width: double.infinity, child: row),
      ),
    );
  }
}
