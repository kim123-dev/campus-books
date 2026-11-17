import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../posts/post_form.dart';
import '../providers.dart';

/// 글쓰기 탭. 등록하면 그 글 상세로 가고 홈 목록을 새로고침한다.
class PostCreateScreen extends ConsumerWidget {
  const PostCreateScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('판매글 작성')),
      body: SafeArea(
        child: PostForm(
          submitLabel: '등록하기',
          // 탭이라 돌아갈 곳은 홈
          onDiscard: () => context.go('/home'),
          onSubmit: (result) async {
            final id = await ref.read(postApiProvider).create({
              ...result.values.toJson(),
              'image_ids': result.pendingImageIds,
            });
            ref.read(postsChangedProvider).value++;
            if (!context.mounted) return;
            // 홈 탭으로 바꾼 뒤 상세를 위에 쌓는다(뒤로 가면 새로고침된 홈 목록).
            context.go('/home');
            context.push('/posts/$id');
          },
        ),
      ),
    );
  }
}
