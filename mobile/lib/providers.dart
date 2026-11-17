import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import 'api/api_client.dart';
import 'api/token_storage.dart';
import 'auth/auth_service.dart';
import 'config.dart';
import 'photos/photo_service.dart';
import 'posts/post_api.dart';
import 'posts/post_events.dart';

/// main()에서 저장된 토큰을 읽은 뒤 덮어쓴다. (첫 화면을 로그인/홈 중 무엇으로 할지 정하려고)
final tokenStorageProvider = Provider<TokenStorage>((ref) => throw UnimplementedError());
final sessionProvider = Provider<Session>((ref) => throw UnimplementedError());

final dioProvider = Provider<Dio>((ref) {
  final session = ref.watch(sessionProvider);
  return createApiDio(
    baseUrl: apiBase,
    storage: ref.watch(tokenStorageProvider),
    onSessionExpired: session.expire,
  );
});

final authServiceProvider = Provider<AuthService>((ref) => AuthService(
      dio: ref.watch(dioProvider),
      storage: ref.watch(tokenStorageProvider),
      session: ref.watch(sessionProvider),
    ));

final postApiProvider = Provider<PostApi>((ref) => PostApi(ref.watch(dioProvider)));

final photoServiceProvider = Provider<PhotoService>((ref) => ApiPhotoService(ref.watch(dioProvider)));
final imagePickerProvider = Provider<ImagePicker>((ref) => ImagePicker());

/// 글을 등록·수정·상태 변경·삭제하면 알린다. 홈 목록·상세·내 글 목록이 듣고 있다가 바로 반영한다.
final postEventsProvider = Provider<PostEvents>((ref) {
  final events = PostEvents();
  ref.onDispose(events.dispose);
  return events;
});
