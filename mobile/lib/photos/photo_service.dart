import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:image_picker/image_picker.dart';

import 'photo_prep.dart';

/// 사진 준비(압축)·올리기·임시 사진 지우기. 테스트에서는 가짜로 바꾼다.
abstract class PhotoService {
  Future<Uint8List> prepare(XFile file);

  /// POST /pending-images. 돌려주는 값은 글을 저장할 때 보낼 임시 사진 번호.
  Future<int> upload(Uint8List jpeg, {required void Function(double) onProgress, CancelToken? cancel});

  /// 글쓰기에서 뺀 사진. 실패해도 서버가 24시간 뒤 정리하므로 기다리거나 알리지 않는다.
  Future<void> deletePending(int id);
}

class ApiPhotoService implements PhotoService {
  ApiPhotoService(this.dio);

  final Dio dio;

  @override
  Future<Uint8List> prepare(XFile file) async => preparePhoto(await file.readAsBytes());

  @override
  Future<int> upload(Uint8List jpeg, {required void Function(double) onProgress, CancelToken? cancel}) async {
    final form = FormData.fromMap({
      'file': MultipartFile.fromBytes(jpeg, filename: 'photo.jpg', contentType: DioMediaType('image', 'jpeg')),
    });
    final response = await dio.post<dynamic>(
      '/pending-images',
      data: form,
      cancelToken: cancel,
      onSendProgress: (sent, total) {
        if (total > 0) onProgress(sent / total);
      },
    );
    return (response.data as Map)['id'] as int;
  }

  @override
  Future<void> deletePending(int id) async {
    try {
      await dio.delete<dynamic>('/pending-images/$id');
    } on DioException {
      // 위 설명대로 무시
    }
  }
}
