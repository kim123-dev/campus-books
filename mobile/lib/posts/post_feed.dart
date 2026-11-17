import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/api_error.dart';
import 'post_api.dart';
import 'post_models.dart';

typedef PostFetcher = Future<PostPage> Function(PostQuery query, int page);

/// 홈 목록 상태: 검색어·판매 완료 보기, 페이지 이어 받기(무한 스크롤), 새로고침.
///
/// 검색할 때마다 세대 번호(_generation)를 올리고, 응답이 왔을 때 번호가 다르면 버린다.
/// 그래서 "책"을 검색하다 "책상"으로 바꿨을 때 "책" 결과가 늦게 와도 화면을 덮어쓰지 않는다.
/// (이어 받기 응답도 같은 방법으로, 검색이 바뀐 뒤 도착하면 버린다)
class PostFeed extends ChangeNotifier {
  PostFeed(this._fetch, {this.debounce = const Duration(milliseconds: 400)});

  final PostFetcher _fetch;

  /// 입력이 멈춘 뒤 검색할 때까지 기다리는 시간
  final Duration debounce;

  PostQuery _query = const PostQuery();
  List<PostSummary> _items = const [];
  int _total = 0;
  int _page = 0;
  bool _loading = false;
  bool _loadingMore = false;
  ApiError? _error;
  ApiError? _moreError;
  int _generation = 0;
  Timer? _debounceTimer;
  bool _disposed = false;

  PostQuery get query => _query;
  List<PostSummary> get items => _items;
  int get total => _total;

  /// 처음 받거나 검색을 바꿔 목록 전체를 새로 받는 중
  bool get loading => _loading;
  bool get loadingMore => _loadingMore;

  /// 첫 페이지를 받지 못함(목록 자리에 오류 화면)
  ApiError? get error => _error;

  /// 다음 페이지를 받지 못함(목록 아래에 다시 시도)
  ApiError? get moreError => _moreError;

  /// 첫 페이지를 받은 적이 있는지 (빈 목록 화면과 로딩 화면을 구별)
  bool get loaded => _page > 0;
  bool get hasMore => loaded && _items.length < _total;

  /// 검색어 입력. 입력이 debounce만큼 멈추면 검색한다.
  void setSearchText(String text) {
    _debounceTimer?.cancel();
    if (text.trim() == _query.q.trim()) return;
    _debounceTimer = Timer(debounce, () => _replaceQuery(_query.copyWith(q: text)));
  }

  /// 키보드의 검색 버튼: 기다리지 않고 바로 검색
  void searchNow(String text) {
    _debounceTimer?.cancel();
    _replaceQuery(_query.copyWith(q: text));
  }

  void setIncludeSold(bool value) {
    if (value == _query.includeSold) return;
    _replaceQuery(_query.copyWith(includeSold: value));
  }

  void _replaceQuery(PostQuery query) {
    _query = query;
    // 이전 조건의 결과는 지우고 로딩 화면을 보여준다(다른 조건의 글이 잠깐이라도 섞여 보이지 않게).
    _items = const [];
    _page = 0;
    _total = 0;
    refresh();
  }

  /// 첫 페이지부터 다시 받는다. 당겨서 새로고침이면 받는 동안 지금 목록을 그대로 둔다.
  Future<void> refresh() async {
    final generation = ++_generation;
    _loading = true;
    _loadingMore = false;
    _error = null;
    _moreError = null;
    _notify();
    try {
      final page = await _fetch(_query, 1);
      if (generation != _generation) return; // 그 사이 검색이 바뀜: 늦게 온 결과는 버린다
      _items = _dedupe(const [], page.items);
      _total = page.total;
      _page = 1;
    } catch (e) {
      if (generation != _generation) return;
      _error = ApiError.from(e);
    } finally {
      if (generation == _generation) {
        _loading = false;
        _notify();
      }
    }
  }

  /// 목록 끝에 가까워지면 다음 페이지를 받는다. 이미 받는 중이거나 더 없으면 아무것도 하지 않는다.
  Future<void> loadMore() async {
    if (!hasMore || _loading || _loadingMore) return;
    final generation = _generation;
    _loadingMore = true;
    _moreError = null;
    _notify();
    try {
      final page = await _fetch(_query, _page + 1);
      if (generation != _generation) return;
      _items = _dedupe(_items, page.items);
      _total = page.total;
      _page = page.page;
      // 그 사이 글이 지워져 빈 페이지가 오면 더 받지 않는다(같은 페이지를 계속 부르지 않게).
      if (page.items.isEmpty) _total = _items.length;
    } catch (e) {
      if (generation != _generation) return;
      _moreError = ApiError.from(e);
    } finally {
      if (generation == _generation) {
        _loadingMore = false;
        _notify();
      }
    }
  }

  /// 페이지를 받는 사이 새 글이 올라오면 앞 페이지의 글이 뒤로 밀려 다음 페이지에 또 나온다. 한 번만 보여준다.
  static List<PostSummary> _dedupe(List<PostSummary> current, List<PostSummary> incoming) {
    final seen = {for (final post in current) post.id};
    return [...current, for (final post in incoming) if (seen.add(post.id)) post];
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _debounceTimer?.cancel();
    super.dispose();
  }
}
