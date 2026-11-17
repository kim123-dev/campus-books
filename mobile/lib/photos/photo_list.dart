import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';

import '../api/api_error.dart';
import '../posts/post_rules.dart';
import 'photo_prep.dart';
import 'photo_service.dart';

enum PhotoState { preparing, uploading, uploaded, failed }

/// 이번에 고른 사진 한 장
class NewPhoto {
  NewPhoto(this.source);

  final XFile source;
  Uint8List? jpeg;
  PhotoState state = PhotoState.preparing;
  double progress = 0;
  int? pendingId;
  String? error;
  CancelToken? _cancel;
}

/// 글에 이미 붙어 있는 사진 (수정 화면). removed면 저장할 때 지운다.
class ExistingPhoto {
  ExistingPhoto({required this.id, required this.thumbnailUrl});

  final int id;
  final String thumbnailUrl;
  bool removed = false;
}

/// 글쓰기·수정 폼의 사진 목록. 고르는 즉시 한 장씩 줄여서 올려 둔다(웹과 같은 흐름).
class PhotoList extends ChangeNotifier {
  PhotoList(this._service, {List<ExistingPhoto> existing = const []}) : existing = List.of(existing);

  final PhotoService _service;
  final List<ExistingPhoto> existing;
  final List<NewPhoto> photos = [];
  final List<Completer<void>> _waiters = [];
  bool _disposed = false;

  int get count => existing.where((p) => !p.removed).length + photos.length;
  int get remaining => maxPhotos - count;

  /// 줄이거나 올리는 중인 사진이 있음
  bool get busy => photos.any((p) => p.state == PhotoState.preparing || p.state == PhotoState.uploading);
  bool get hasFailed => photos.any((p) => p.state == PhotoState.failed);

  /// 저장할 때 보낼 임시 사진 번호(고른 순서대로)
  List<int> get pendingIds => [for (final p in photos) if (p.pendingId != null) p.pendingId!];
  List<int> get removedExistingIds => [for (final p in existing) if (p.removed) p.id];
  bool get changed => photos.isNotEmpty || existing.any((p) => p.removed);

  /// 고른 사진을 더한다. 한도를 넘는 사진은 빼고 안내 문구를 돌려준다.
  String? addAll(List<XFile> files) {
    final accepted = files.take(remaining.clamp(0, maxPhotos)).toList();
    for (final file in accepted) {
      final photo = NewPhoto(file);
      photos.add(photo);
      _process(photo);
    }
    _notify();
    final skipped = files.length - accepted.length;
    return skipped > 0 ? '사진은 $maxPhotos장까지 올릴 수 있어 $skipped장은 빼었습니다.' : null;
  }

  /// 실패한 사진 다시 올리기(줄이기에서 실패했으면 줄이기부터)
  void retry(NewPhoto photo) {
    if (photo.state != PhotoState.failed) return;
    _process(photo);
  }

  void remove(NewPhoto photo) {
    photo._cancel?.cancel();
    photos.remove(photo);
    if (photo.pendingId != null) _service.deletePending(photo.pendingId!);
    _notify();
  }

  /// 기존 사진 빼기·되돌리기. 되돌릴 자리가 없으면 안내 문구.
  String? toggleExisting(ExistingPhoto photo) {
    if (photo.removed && remaining <= 0) return '사진은 $maxPhotos장까지라 되돌리려면 새 사진을 먼저 빼 주세요.';
    photo.removed = !photo.removed;
    _notify();
    return null;
  }

  /// 줄이기·올리기가 모두 끝날 때까지 기다린다(등록 버튼을 누른 뒤).
  Future<void> settled() {
    if (!busy) return Future.value();
    final waiter = Completer<void>();
    _waiters.add(waiter);
    return waiter.future;
  }

  /// 저장이 끝난 뒤 폼을 비운다. 글에 붙은 임시 사진은 지우지 않는다.
  void clearAfterSave() {
    photos.clear();
    existing.clear();
    _notify();
  }

  Future<void> _process(NewPhoto photo) async {
    photo
      ..error = null
      ..progress = 0
      ..state = photo.jpeg == null ? PhotoState.preparing : PhotoState.uploading;
    _notify();
    try {
      photo.jpeg ??= await _service.prepare(photo.source);
      if (!photos.contains(photo)) return; // 그 사이 뺐음
      photo.state = PhotoState.uploading;
      photo._cancel = CancelToken();
      _notify();
      final id = await _service.upload(
        photo.jpeg!,
        cancel: photo._cancel,
        onProgress: (value) {
          photo.progress = value;
          _notify();
        },
      );
      if (!photos.contains(photo)) {
        _service.deletePending(id); // 올라가는 사이 뺐으면 서버에서도 지운다
        return;
      }
      photo
        ..pendingId = id
        ..state = PhotoState.uploaded;
    } on PhotoPrepError catch (e) {
      photo
        ..state = PhotoState.failed
        ..error = e.message;
    } catch (e) {
      if (e is DioException && CancelToken.isCancel(e)) return;
      photo
        ..state = PhotoState.failed
        // 413(25MB)·422(형식)·429(올리기 횟수) 등 서버 문구 그대로
        ..error = ApiError.from(e).message;
    } finally {
      _notify();
    }
  }

  void _notify() {
    if (!busy) {
      for (final waiter in _waiters) {
        waiter.complete();
      }
      _waiters.clear();
    }
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    for (final photo in photos) {
      photo._cancel?.cancel();
    }
    super.dispose();
  }
}
