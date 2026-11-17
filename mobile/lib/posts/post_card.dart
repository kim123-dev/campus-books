import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import 'post_format.dart';
import 'post_models.dart';

/// 목록 카드: 대표 사진, 제목, 가격, 판매 상태, 올린 시간
class PostCard extends StatelessWidget {
  const PostCard({super.key, required this.post, required this.imageBase, required this.onTap, this.now});

  final PostSummary post;

  /// 사진 주소 앞에 붙일 서버 주소
  final String imageBase;
  final VoidCallback onTap;

  /// 테스트에서 "올린 시간"을 고정하려고
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sold = post.status == 'SOLD';
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Opacity(
              opacity: sold ? 0.5 : 1,
              child: PostThumbnail(url: post.thumbnailUrl == null ? null : '$imageBase${post.thumbnailUrl}', size: 88),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(post.title, maxLines: 2, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(
                    formatPrice(post.price),
                    key: const Key('price'),
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      StatusBadge(status: post.status),
                      Text(
                        formatPostedAt(post.createdAt, now: now),
                        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (background, foreground) = switch (status) {
      'RESERVED' => (scheme.tertiaryContainer, scheme.onTertiaryContainer),
      'SOLD' => (scheme.surfaceContainerHighest, scheme.onSurfaceVariant),
      _ => (scheme.primaryContainer, scheme.onPrimaryContainer),
    };
    return DecoratedBox(
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(6)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        child: Text(statusLabels[status] ?? status, style: TextStyle(color: foreground, fontSize: 12)),
      ),
    );
  }
}

/// 네모난 사진. 받는 동안·사진이 없을 때·실패했을 때 자리 표시를 보여준다.
class PostThumbnail extends StatelessWidget {
  const PostThumbnail({super.key, required this.url, required this.size});

  final String? url;
  final double size;

  @override
  Widget build(BuildContext context) {
    final placeholder = ColoredBox(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: Icon(Icons.menu_book_outlined, color: Theme.of(context).colorScheme.outline),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: SizedBox.square(
        dimension: size,
        child: url == null
            ? placeholder
            : CachedNetworkImage(
                imageUrl: url!,
                fit: BoxFit.cover,
                // 화면 크기에 맞게 줄여서 메모리에 둔다(목록이 길어져도 메모리가 덜 든다).
                memCacheWidth: (size * MediaQuery.devicePixelRatioOf(context)).round(),
                placeholder: (_, _) => placeholder,
                errorWidget: (_, _, _) => placeholder,
              ),
      ),
    );
  }
}
