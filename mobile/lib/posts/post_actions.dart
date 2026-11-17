import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../providers.dart';
import 'post_events.dart';
import 'post_format.dart';
import 'post_models.dart';

/// 지금 상태에서 바꿀 수 있는 상태(웹 post.js의 ALLOWED_TRANSITIONS와 같음)
const allowedTransitions = {
  'ON_SALE': ['RESERVED', 'SOLD'],
  'RESERVED': ['ON_SALE', 'SOLD'],
  'SOLD': ['ON_SALE'],
};

/// 상태 바꾸기 버튼·메뉴 문구(웹과 같음). 판매 완료를 되돌릴 때만 문구가 다르다.
String statusChangeLabel(String from, String to) {
  if (from == 'SOLD' && to == 'ON_SALE') return '판매 중으로 되돌리기';
  return _statusTo[to] ?? to;
}

const _statusTo = {'ON_SALE': '판매 중으로 변경', 'RESERVED': '예약 중으로 변경', 'SOLD': '판매 완료로 변경'};
const _statusDone = {'ON_SALE': '판매 중으로 바꿨어요.', 'RESERVED': '예약 중으로 바꿨어요.', 'SOLD': '판매 완료로 바꿨어요.'};

/// 판매 완료된 글은 서버가 수정을 막는다(400). 웹처럼 수정 버튼을 숨기고 이 안내를 보여준다.
const soldNotice = '판매 완료된 글은 수정할 수 없어요. 후기를 남기기 전이면 판매 중으로 되돌릴 수 있어요.';

/// 상세·수정 화면에서 빠져나와 아래에 있던 목록(홈이나 내 정보 탭)으로 돌아가고 안내를 띄운다.
void leaveToList(BuildContext context, String message) {
  final messenger = ScaffoldMessenger.of(context);
  Navigator.of(context).popUntil((route) => route.isFirst);
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

void showMessage(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

/// 상태 변경·삭제의 공통 오류 처리.
/// 404(이미 삭제된 글)·403(내 글이 아님)은 서버 문구와 함께 목록으로, 그 밖은 서버 문구만 띄운다.
void handlePostActionError(BuildContext context, WidgetRef ref, int postId, Object error) {
  final apiError = ApiError.from(error);
  if (!context.mounted) return;
  if (apiError.status == 404) {
    // 목록에도 남아 있지 않게 지운 것으로 알린다.
    ref.read(postEventsProvider).emit(PostEvent.deleted(postId));
  }
  if (apiError.status == 404 || apiError.status == 403) {
    leaveToList(context, apiError.message);
  } else {
    showMessage(context, apiError.message);
  }
}

/// 판매 상태 바꾸기. 판매 완료는 거래한 사람을 고르고, 판매 완료 되돌리기는 한 번 확인한다(웹과 같음).
/// 바뀌면 최신 글을 돌려주고 모든 목록에 알린다. 취소하거나 실패하면 null.
Future<PostDetail?> changePostStatus(BuildContext context, WidgetRef ref, PostSummary post, String to) async {
  final api = ref.read(postApiProvider);
  try {
    int? buyerId;
    if (to == 'SOLD') {
      final candidates = await api.buyerCandidates(post.id);
      if (!context.mounted) return null;
      final picked = await showDialog<_BuyerChoice>(
        context: context,
        builder: (_) => _SellDialog(candidates: candidates),
      );
      if (picked == null) return null;
      buyerId = picked.buyerId;
    } else if (post.status == 'SOLD') {
      final ok = await confirm(
        context,
        title: '판매 중으로 되돌릴까요?',
        body: '거래한 사람 기록이 지워져 서로 후기를 남길 수 없게 돼요.',
        action: '되돌리기',
      );
      if (!ok) return null;
    }
    final updated = await api.changeStatus(post.id, to, buyerId: buyerId);
    ref.read(postEventsProvider).emit(PostEvent.updated(updated));
    if (context.mounted) showMessage(context, _statusDone[to] ?? '상태를 바꿨어요.');
    return updated;
  } catch (e) {
    if (context.mounted) handlePostActionError(context, ref, post.id, e);
    return null;
  }
}

/// 글 삭제: 확인 창을 띄운 뒤 지운다. 지우면 모든 목록에서 빠지고, 상세에 있었으면 목록으로 돌아간다.
Future<bool> deletePost(BuildContext context, WidgetRef ref, int postId) async {
  final ok = await confirm(
    context,
    title: '이 글을 삭제할까요?',
    body: '삭제한 글은 되돌릴 수 없습니다.',
    action: '삭제',
    destructive: true,
  );
  if (!ok || !context.mounted) return false;
  try {
    await ref.read(postApiProvider).delete(postId);
    ref.read(postEventsProvider).emit(PostEvent.deleted(postId));
    if (context.mounted) leaveToList(context, '글을 삭제했습니다.');
    return true;
  } catch (e) {
    if (context.mounted) handlePostActionError(context, ref, postId, e);
    return false;
  }
}

Future<bool> confirm(
  BuildContext context, {
  required String title,
  required String body,
  required String action,
  bool destructive = false,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(body),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('취소')),
        TextButton(
          key: const Key('confirm-action'),
          style: destructive ? TextButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error) : null,
          onPressed: () => Navigator.pop(context, true),
          child: Text(action),
        ),
      ],
    ),
  );
  return result == true;
}

/// 판매 완료 창에서 고른 값. buyerId가 null이면 "선택 안 함"(오프라인 거래 등).
class _BuyerChoice {
  const _BuyerChoice(this.buyerId);

  final int? buyerId;
}

/// 판매 완료: 이 글로 쪽지를 주고받은 사람 중 거래한 사람을 고른다(웹 buyer 창과 같은 문구).
class _SellDialog extends StatefulWidget {
  const _SellDialog({required this.candidates});

  final List<BuyerCandidate> candidates;

  @override
  State<_SellDialog> createState() => _SellDialogState();
}

class _SellDialogState extends State<_SellDialog> {
  // -1: 아직 안 고름, 0: 선택 안 함, 그 밖: 구매자 번호
  int _choice = -1;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: const Text('판매 완료로 변경'),
      content: SingleChildScrollView(
        child: RadioGroup<int>(
          groupValue: _choice,
          onChanged: (value) => setState(() => _choice = value ?? -1),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('후기가 남은 뒤에는 판매 중으로 되돌릴 수 없어요. 거래한 사람은 후기를 남기기 전까지 바꿀 수 있어요.'),
              const SizedBox(height: 12),
              Text('거래한 사람', style: theme.textTheme.titleSmall),
              if (widget.candidates.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text('이 글로 쪽지를 주고받은 사람이 없어요.', style: TextStyle(color: theme.colorScheme.outline)),
                ),
              for (final c in widget.candidates)
                RadioListTile<int>(value: c.id, title: Text(c.nickname), contentPadding: EdgeInsets.zero),
              const RadioListTile<int>(value: 0, title: Text('선택 안 함 (오프라인 거래 등)'), contentPadding: EdgeInsets.zero),
              Text('고른 사람과는 서로 한 번씩 거래 후기를 남길 수 있어요.', style: theme.textTheme.bodySmall),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('취소')),
        TextButton(
          onPressed: _choice < 0 ? null : () => Navigator.pop(context, _BuyerChoice(_choice == 0 ? null : _choice)),
          child: const Text('판매 완료'),
        ),
      ],
    );
  }
}

/// 상태 바꾸기 버튼을 눌렀을 때: 바꿀 수 있는 상태를 아래에서 고르게 한다.
Future<PostDetail?> chooseStatus(BuildContext context, WidgetRef ref, PostSummary post) async {
  final to = await showModalBottomSheet<String>(
    context: context,
    // 하단 탭 위로 띄운다(내 정보 탭 안에서 열 때 탭 막대에 가려지지 않게).
    useRootNavigator: true,
    builder: (context) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(title: Text('지금: ${statusLabels[post.status] ?? post.status}')),
          for (final next in allowedTransitions[post.status] ?? const <String>[])
            ListTile(
              leading: const Icon(Icons.swap_horiz),
              title: Text(statusChangeLabel(post.status, next)),
              onTap: () => Navigator.pop(context, next),
            ),
        ],
      ),
    ),
  );
  if (to == null || !context.mounted) return null;
  return changePostStatus(context, ref, post, to);
}
