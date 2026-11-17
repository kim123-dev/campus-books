import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../posts/post_card.dart';
import '../posts/post_events.dart';
import '../posts/post_feed.dart';
import '../providers.dart';
import '../widgets/state_views.dart';

/// 홈: 검색, 판매 완료 보기, 글 목록(무한 스크롤, 당겨서 새로고침). 로그인하지 않아도 볼 수 있다(웹과 같음).
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  late final PostFeed _feed;
  final _search = TextEditingController();
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    final api = ref.read(postApiProvider);
    _feed = PostFeed(api.list)..refresh();
    _scroll.addListener(_maybeLoadMore);
    // 다른 화면에서 글을 쓰거나 바꾸거나 지우면 목록에 바로 반영한다.
    _events = ref.read(postEventsProvider)..addListener(_onPostEvent);
  }

  late final PostEvents _events;

  void _onPostEvent() {
    final event = _events.value;
    if (event != null) _feed.apply(event);
  }

  @override
  void dispose() {
    _events.removeListener(_onPostEvent);
    _feed.dispose();
    _search.dispose();
    _scroll.dispose();
    super.dispose();
  }

  /// 끝에서 화면 하나 높이쯤 남으면 다음 페이지를 미리 받는다.
  void _maybeLoadMore() {
    final position = _scroll.position;
    if (position.pixels >= position.maxScrollExtent - position.viewportDimension) _feed.loadMore();
  }

  @override
  Widget build(BuildContext context) {
    final imageBase = ref.watch(dioProvider).options.baseUrl;
    return Scaffold(
      appBar: AppBar(
        title: const Text('캠퍼스북스'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(112),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
            child: Column(
              children: [
                TextField(
                  key: const Key('search'),
                  controller: _search,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: '제목·교재명·과목명 검색',
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    suffixIcon: ListenableBuilder(
                      listenable: _search,
                      builder: (context, _) => _search.text.isEmpty
                          ? const SizedBox.shrink()
                          : IconButton(
                              tooltip: '지우기',
                              icon: const Icon(Icons.clear),
                              onPressed: () {
                                _search.clear();
                                _feed.searchNow('');
                              },
                            ),
                    ),
                  ),
                  onChanged: _feed.setSearchText,
                  onSubmitted: _feed.searchNow,
                ),
                ListenableBuilder(
                  listenable: _feed,
                  builder: (context, _) => SwitchListTile(
                    key: const Key('include-sold'),
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: const Text('판매 완료 글도 보기'),
                    value: _feed.query.includeSold,
                    onChanged: _feed.setIncludeSold,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
      body: ListenableBuilder(
        listenable: _feed,
        builder: (context, _) => RefreshIndicator(
          onRefresh: _feed.refresh,
          child: _body(imageBase),
        ),
      ),
    );
  }

  Widget _body(String imageBase) {
    final feed = _feed;
    // 첫 페이지를 받는 중(검색을 바꾼 직후 포함)
    if (!feed.loaded && feed.loading) return const LoadingView();
    if (!feed.loaded && feed.error != null) {
      return ErrorView(message: feed.error!.message, onRetry: feed.refresh);
    }
    if (feed.loaded && feed.items.isEmpty) {
      final searching = feed.query.q.trim().isNotEmpty;
      return MessageView(
        icon: Icons.menu_book_outlined,
        title: searching ? '검색 결과가 없습니다' : '아직 올라온 글이 없습니다',
        body: searching
            ? '다른 검색어로 찾아보세요.${feed.query.includeSold ? '' : ' 판매 완료 글은 숨겨져 있어요.'}'
            : null,
      );
    }
    return ListView.separated(
      key: const Key('post-list'),
      controller: _scroll,
      physics: const AlwaysScrollableScrollPhysics(),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      itemCount: feed.items.length + 1,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        if (index == feed.items.length) return _footer();
        final post = feed.items[index];
        return PostCard(post: post, imageBase: imageBase, onTap: () => context.push('/posts/${post.id}'));
      },
    );
  }

  /// 목록 끝: 더 받는 중 / 다시 시도 / 끝
  Widget _footer() {
    final feed = _feed;
    if (feed.loadingMore) {
      return const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()));
    }
    if (feed.moreError != null) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text(feed.moreError!.message, textAlign: TextAlign.center),
            TextButton(onPressed: feed.loadMore, child: const Text('다시 시도')),
          ],
        ),
      );
    }
    if (feed.hasMore) {
      // 목록이 화면보다 짧아 스크롤할 수 없을 때도 이어 받도록 그려질 때 한 번 부른다.
      WidgetsBinding.instance.addPostFrameCallback((_) => feed.loadMore());
      return const SizedBox(height: 48);
    }
    return const SizedBox(height: 24);
  }
}
