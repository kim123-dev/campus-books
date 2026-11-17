import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_error.dart';
import '../posts/post_actions.dart';
import '../posts/post_card.dart';
import '../posts/post_events.dart';
import '../posts/post_models.dart';
import '../providers.dart';

/// 내 정보: 닉네임·이메일, 로그아웃, 내 글 목록(판매 상태별로 나눠서, 글마다 수정·상태 변경·삭제).
class MeScreen extends ConsumerStatefulWidget {
  const MeScreen({super.key});

  @override
  ConsumerState<MeScreen> createState() => _MeScreenState();
}

/// 내 글을 나눠 보여줄 순서(웹과 같은 상태 값)
const _statusOrder = ['ON_SALE', 'RESERVED', 'SOLD'];

class _MeScreenState extends ConsumerState<MeScreen> {
  Map<String, dynamic>? _me;
  ApiError? _meError;
  List<PostSummary>? _posts;
  ApiError? _postsError;
  late final PostEvents _events;

  @override
  void initState() {
    super.initState();
    _refresh();
    // 상세·수정 화면이나 글쓰기 탭에서 바꾼 내용을 다시 열지 않아도 반영한다.
    _events = ref.read(postEventsProvider)..addListener(_onPostEvent);
  }

  @override
  void dispose() {
    _events.removeListener(_onPostEvent);
    super.dispose();
  }

  void _onPostEvent() {
    final event = _events.value;
    final posts = _posts;
    if (event == null || posts == null) return;
    // 내 글 목록은 판매 완료도 보여주므로 숨길 글이 없다.
    final next = applyPostEvent(posts, event, visible: (_) => true);
    if (next == null) {
      _loadPosts();
    } else {
      setState(() => _posts = next);
    }
  }

  Future<void> _refresh() => Future.wait([_loadMe(), _loadPosts()]);

  Future<void> _loadMe() async {
    try {
      final response = await ref.read(dioProvider).get<dynamic>('/users/me');
      if (!mounted) return;
      setState(() {
        _me = response.data as Map<String, dynamic>;
        _meError = null;
      });
    } catch (e) {
      if (mounted) setState(() => _meError = ApiError.from(e));
    }
  }

  Future<void> _loadPosts() async {
    try {
      final posts = await ref.read(postApiProvider).myPosts();
      if (!mounted) return;
      setState(() {
        _posts = posts;
        _postsError = null;
      });
    } catch (e) {
      if (mounted) setState(() => _postsError = ApiError.from(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('내 정보'),
        actions: [
          TextButton(onPressed: () => ref.read(authServiceProvider).logout(), child: const Text('로그아웃')),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            _profile(),
            const Divider(height: 1),
            ..._myPosts(),
          ],
        ),
      ),
    );
  }

  Widget _profile() {
    final theme = Theme.of(context);
    final me = _me;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: me != null
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${me['nickname']}', style: theme.textTheme.headlineSmall),
                const SizedBox(height: 4),
                Text('${me['email']}'),
              ],
            )
          : _meError != null
              ? Text(_meError!.message)
              : const Center(child: CircularProgressIndicator()),
    );
  }

  List<Widget> _myPosts() {
    final theme = Theme.of(context);
    final posts = _posts;
    final header = Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(posts == null ? '내 글' : '내 글 ${posts.length}개', style: theme.textTheme.titleMedium),
    );
    if (posts == null) {
      return [
        header,
        Padding(
          padding: const EdgeInsets.all(24),
          child: _postsError == null
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  children: [
                    Text(_postsError!.message, textAlign: TextAlign.center),
                    TextButton(onPressed: _loadPosts, child: const Text('다시 시도')),
                  ],
                ),
        ),
      ];
    }
    if (posts.isEmpty) {
      return [
        header,
        Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              Text('아직 작성한 글이 없습니다.', style: TextStyle(color: theme.colorScheme.outline)),
              const SizedBox(height: 12),
              FilledButton(onPressed: () => context.go('/sell'), child: const Text('글쓰기')),
            ],
          ),
        ),
      ];
    }
    final imageBase = ref.watch(dioProvider).options.baseUrl;
    return [
      header,
      for (final status in _statusOrder) ...[
        if (posts.any((post) => post.status == status)) ...[
          Padding(
            key: Key('section-$status'),
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Row(
              children: [
                StatusBadge(status: status),
                const SizedBox(width: 8),
                Text('${posts.where((post) => post.status == status).length}개', style: theme.textTheme.bodySmall),
              ],
            ),
          ),
          for (final post in posts.where((post) => post.status == status))
            PostCard(
              key: Key('my-post-${post.id}'),
              post: post,
              imageBase: imageBase,
              onTap: () => context.push('/posts/${post.id}'),
              trailing: _menu(post),
            ),
        ],
      ],
    ];
  }

  /// 글마다: 수정(판매 완료는 서버가 막아 빼 둔다), 판매 상태 바꾸기, 삭제
  Widget _menu(PostSummary post) {
    return PopupMenuButton<String>(
      tooltip: '글 관리',
      icon: const Icon(Icons.more_vert),
      onSelected: (action) {
        switch (action) {
          case 'edit':
            context.push('/posts/${post.id}/edit');
          case 'delete':
            deletePost(context, ref, post.id);
          default:
            changePostStatus(context, ref, post, action);
        }
      },
      itemBuilder: (context) => [
        if (post.status != 'SOLD') const PopupMenuItem(value: 'edit', child: Text('수정')),
        for (final next in allowedTransitions[post.status] ?? const <String>[])
          PopupMenuItem(value: next, child: Text(statusChangeLabel(post.status, next))),
        PopupMenuItem(
          value: 'delete',
          child: Text('삭제', style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
      ],
    );
  }
}
