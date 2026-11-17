import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../api/api_error.dart';
import '../auth/auth_service.dart';
import '../photos/photo_list.dart';
import '../providers.dart';
import 'post_format.dart';
import 'post_rules.dart';

/// 저장할 때 화면이 넘겨받는 값. 수정(6단계)은 removedImageIds도 쓴다.
class PostFormResult {
  const PostFormResult({required this.values, required this.pendingImageIds, required this.removedImageIds});

  final PostFormValues values;
  final List<int> pendingImageIds;
  final List<int> removedImageIds;
}

/// 글쓰기·수정 공용 폼: 제목·교재명·과목명·학교·책 상태·가격·설명·사진(최대 3장).
///
/// - 사진은 고르는 즉시 줄여서 올려 두고(장마다 진행률·다시 올리기·빼기), 저장할 때 번호만 보낸다(웹과 같음).
/// - 등록 버튼은 누른 순간부터 끝날 때까지 비활성화한다(두 번 등록 방지).
/// - 쓰던 내용이 있으면 뒤로 가기 전에 확인한다.
class PostForm extends ConsumerStatefulWidget {
  const PostForm({
    super.key,
    required this.submitLabel,
    required this.onSubmit,
    this.initial = const PostFormValues(),
    this.existingImages = const [],
    this.preselectMySchool = true,
    this.onDiscard,
  });

  final String submitLabel;

  /// 저장 요청. 서버 오류는 그대로 던지면 폼이 칸·아래 안내에 보여준다. 성공하면 폼이 비워진다.
  final Future<void> Function(PostFormResult result) onSubmit;
  final PostFormValues initial;
  final List<ExistingPhoto> existingImages;

  /// 새 글: 학교 칸이 비어 있으면 내 학교를 미리 고른다(웹과 같음).
  final bool preselectMySchool;

  /// 쓰던 내용을 버리기로 했을 때(뒤로 가기 확인 후). 없으면 Navigator.pop.
  final VoidCallback? onDiscard;

  @override
  ConsumerState<PostForm> createState() => PostFormState();
}

class PostFormState extends ConsumerState<PostForm> {
  late final _title = TextEditingController(text: widget.initial.title);
  late final _bookTitle = TextEditingController(text: widget.initial.bookTitle);
  late final _courseName = TextEditingController(text: widget.initial.courseName);
  late final _price = TextEditingController(text: widget.initial.price);
  late final _description = TextEditingController(text: widget.initial.description);
  late String? _condition = widget.initial.condition;
  late int? _schoolId = widget.initial.schoolId;
  late final PhotoList _photos = PhotoList(ref.read(photoServiceProvider), existing: widget.existingImages);

  List<School> _schools = const [];
  bool _noMySchool = false;
  Map<String, String> _errors = const {};
  String? _generalError;
  bool _submitting = false;
  bool _waitingPhotos = false;

  List<TextEditingController> get _texts => [_title, _bookTitle, _courseName, _price, _description];

  /// 처음 값에서 바뀐 것이 있는지(뒤로 가기 확인용)
  bool get dirty {
    final now = _values;
    final first = widget.initial;
    return now.title != first.title ||
        now.bookTitle != first.bookTitle ||
        now.courseName != first.courseName ||
        now.price != first.price ||
        now.description != first.description ||
        now.condition != first.condition ||
        _photos.changed;
  }

  PostFormValues get _values => PostFormValues(
        title: _title.text,
        bookTitle: _bookTitle.text,
        courseName: _courseName.text,
        condition: _condition,
        price: _price.text,
        description: _description.text,
        schoolId: _schoolId,
      );

  @override
  void initState() {
    super.initState();
    for (final c in _texts) {
      c.addListener(_rebuild);
    }
    _photos.addListener(_rebuild);
    _loadSchools();
    _restoreLostPhotos();
  }

  @override
  void dispose() {
    for (final c in _texts) {
      c.dispose();
    }
    _photos.dispose();
    super.dispose();
  }

  void _rebuild() {
    if (mounted) setState(() {});
  }

  Future<void> _loadSchools() async {
    try {
      final schools = await ref.read(authServiceProvider).schools();
      final mine = await ref.read(postApiProvider).mySchool();
      if (!mounted) return;
      setState(() {
        _schools = schools;
        _noMySchool = mine == null;
        if (widget.preselectMySchool && _schoolId == null && mine != null && schools.any((s) => s.id == mine)) {
          _schoolId = mine;
        }
      });
    } catch (_) {
      // 학교는 선택 항목이라 목록을 못 받아도 글을 쓸 수 있다.
    }
  }

  /// 카메라를 켠 사이 안드로이드가 앱을 종료했으면, 다시 열었을 때 찍은 사진을 되살린다.
  Future<void> _restoreLostPhotos() async {
    try {
      final lost = await ref.read(imagePickerProvider).retrieveLostData();
      if (lost.isEmpty || lost.files == null || !mounted) return;
      final skipped = _photos.addAll(lost.files!);
      _toast(skipped ?? '앱이 다시 시작되어, 찍어 둔 사진을 되살렸어요.');
    } catch (_) {}
  }

  void _toast(String message) {
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _pick(ImageSource source) async {
    final picker = ref.read(imagePickerProvider);
    final remaining = _photos.remaining;
    if (remaining <= 0) return;
    try {
      final List<XFile> files;
      if (source == ImageSource.camera) {
        final file = await picker.pickImage(source: ImageSource.camera);
        files = file == null ? const [] : [file];
      } else if (remaining == 1) {
        final file = await picker.pickImage(source: ImageSource.gallery);
        files = file == null ? const [] : [file];
      } else {
        // 안드로이드 사진 선택기(저장소 권한 없음). main()에서 켠다.
        files = await picker.pickMultiImage(limit: remaining);
      }
      if (files.isEmpty || !mounted) return;
      final skipped = _photos.addAll(files);
      if (skipped != null) _toast(skipped);
    } catch (_) {
      _toast(source == ImageSource.camera ? '카메라를 열 수 없습니다.' : '사진을 불러올 수 없습니다.');
    }
  }

  Future<void> _choosePhotoSource() async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      // 하단 탭 위로 띄운다(탭 안 화면이라 기본값이면 탭 막대 아래에 가려진다).
      useRootNavigator: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('카메라로 찍기'),
              onTap: () => Navigator.pop(context, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('앨범에서 고르기'),
              onTap: () => Navigator.pop(context, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source != null) await _pick(source);
  }

  Future<void> _submit() async {
    // 누르자마자(첫 await 전에) 막아야 빠르게 두 번 눌러도 한 번만 등록된다.
    if (_submitting) return;
    setState(() => _submitting = true);
    try {
      final values = _values;
      final errors = validatePost(values);
      setState(() {
        _errors = errors;
        _generalError = errors.isEmpty ? null : '입력값을 확인해 주세요.';
      });
      if (errors.isNotEmpty) return;
      FocusScope.of(context).unfocus();

      if (_photos.busy) {
        setState(() => _waitingPhotos = true);
        await _photos.settled();
        if (!mounted) return;
        setState(() => _waitingPhotos = false);
      }
      if (_photos.hasFailed) {
        setState(() => _generalError = '올리지 못한 사진이 있습니다. 다시 시도하거나 빼 주세요.');
        return;
      }

      await widget.onSubmit(PostFormResult(
        values: values,
        pendingImageIds: _photos.pendingIds,
        removedImageIds: _photos.removedExistingIds,
      ));
      if (mounted) _clear();
    } catch (e) {
      final error = ApiError.from(e);
      if (mounted) {
        setState(() {
          _errors = error.fieldErrors;
          _generalError = error.message;
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
          _waitingPhotos = false;
        });
      }
    }
  }

  void _clear() {
    for (final c in _texts) {
      c.clear();
    }
    _photos.clearAfterSave();
    setState(() {
      _condition = null;
      _errors = const {};
      _generalError = null;
    });
  }

  Future<void> _confirmDiscard() async {
    final discard = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('작성 중인 내용이 사라져요'),
        content: const Text('지금 나가면 입력한 내용과 고른 사진이 저장되지 않아요.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('계속 쓰기')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('나가기')),
        ],
      ),
    );
    if (discard != true || !mounted) return;
    _clear();
    if (widget.onDiscard != null) {
      widget.onDiscard!();
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final errorColor = Theme.of(context).colorScheme.error;
    return PopScope(
      canPop: !dirty && !_submitting,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && !_submitting) _confirmDiscard();
      },
      child: ListView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          _PhotoStrip(photos: _photos, onAdd: _submitting ? null : _choosePhotoSource, imageBase: ref.watch(dioProvider).options.baseUrl, onMessage: _toast),
          const SizedBox(height: 16),
          _text('title', _title, '제목', maxLength: titleMax),
          _text('book_title', _bookTitle, '교재명', maxLength: bookTitleMax),
          _text('course_name', _courseName, '과목명 (선택)',
              helper: '목록의 과목명 필터는 정확히 일치할 때만 찾습니다.', maxLength: courseNameMax),
          DropdownButtonFormField<int?>(
            key: const Key('school'),
            initialValue: _schoolId,
            isExpanded: true,
            decoration: InputDecoration(
              labelText: '학교 (선택)',
              helperText: _schoolId == null && _noMySchool ? '학교 없이 올리면 학교별 목록에 안 보여요' : null,
              errorText: _errors['school_id'],
            ),
            items: [
              const DropdownMenuItem<int?>(value: null, child: Text('선택 안 함')),
              for (final s in _schools) DropdownMenuItem<int?>(value: s.id, child: Text(s.name)),
              // 목록에 없는 학교(그 사이 비활성)로 쓴 글을 수정할 때도 그대로 둘 수 있게
              if (_schoolId != null && !_schools.any((s) => s.id == _schoolId))
                DropdownMenuItem<int?>(value: _schoolId, child: Text('현재 학교 (#$_schoolId)')),
            ],
            onChanged: _submitting ? null : (value) => setState(() => _schoolId = value),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            key: const Key('condition'),
            initialValue: _condition,
            decoration: InputDecoration(labelText: '책 상태', errorText: _errors['condition']),
            hint: const Text('선택해 주세요'),
            items: [
              for (final entry in conditionLabels.entries) DropdownMenuItem(value: entry.key, child: Text(entry.value)),
            ],
            onChanged: _submitting ? null : (value) => setState(() => _condition = value),
          ),
          const SizedBox(height: 12),
          _text(
            'price',
            _price,
            '가격 (원)',
            helper: _priceHelper(),
            keyboardType: TextInputType.number,
            formatters: [FilteringTextInputFormatter.digitsOnly],
            maxLength: 8,
          ),
          _text('description', _description, '설명 (선택)', maxLength: descriptionMax, lines: 6, showCounter: true),
          if (_generalError != null) ...[
            Text(_generalError!, key: const Key('form-error'), style: TextStyle(color: errorColor)),
            const SizedBox(height: 8),
          ],
          FilledButton(
            key: const Key('post-submit'),
            onPressed: _submitting ? null : _submit,
            child: Text(_waitingPhotos ? '사진 올리는 중…' : _submitting ? '저장 중…' : widget.submitLabel),
          ),
        ],
      ),
    );
  }

  /// 0원이면 무료 나눔 안내, 금액을 적으면 쉼표 붙인 값을 보여준다(긴 숫자를 잘못 적지 않게).
  String _priceHelper() {
    final price = int.tryParse(_price.text);
    if (price == null || price == 0) return '0원이면 무료 나눔으로 표시됩니다.';
    return formatPrice(price);
  }

  Widget _text(
    String name,
    TextEditingController controller,
    String label, {
    String? helper,
    int? maxLength,
    int lines = 1,
    bool showCounter = false,
    TextInputType? keyboardType,
    List<TextInputFormatter>? formatters,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        key: Key(name),
        controller: controller,
        enabled: !_submitting,
        maxLength: maxLength,
        minLines: lines,
        maxLines: lines == 1 ? 1 : null,
        keyboardType: lines > 1 ? TextInputType.multiline : keyboardType,
        inputFormatters: formatters,
        textInputAction: lines > 1 ? TextInputAction.newline : TextInputAction.next,
        decoration: InputDecoration(
          labelText: label,
          alignLabelWithHint: lines > 1,
          helperText: helper,
          helperMaxLines: 2,
          errorText: _errors[name],
          errorMaxLines: 3,
          counterText: showCounter ? null : '',
        ),
      ),
    );
  }
}

/// 사진 줄: 기존 사진(수정), 새 사진(진행률·실패·다시 올리기·빼기), 추가 버튼
class _PhotoStrip extends StatelessWidget {
  const _PhotoStrip({required this.photos, required this.onAdd, required this.imageBase, required this.onMessage});

  final PhotoList photos;
  final VoidCallback? onAdd;
  final String imageBase;
  final void Function(String) onMessage;

  static const _size = 96.0;

  @override
  Widget build(BuildContext context) {
    final failed = photos.photos.where((p) => p.error != null).map((p) => p.error!).toSet();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('사진 (선택, 최대 $maxPhotos장)', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final (i, p) in photos.existing.indexed)
                _tile(
                  context,
                  image: Image.network('$imageBase${p.thumbnailUrl}', fit: BoxFit.cover),
                  label: '올린 사진 ${i + 1}',
                  dimmed: p.removed,
                  overlay: p.removed ? const Text('삭제 예정', style: TextStyle(color: Colors.white)) : null,
                  actionIcon: p.removed ? Icons.undo : Icons.close,
                  actionLabel: p.removed ? '올린 사진 ${i + 1} 되돌리기' : '올린 사진 ${i + 1} 빼기',
                  onAction: () {
                    final message = photos.toggleExisting(p);
                    if (message != null) onMessage(message);
                  },
                ),
              for (final (i, p) in photos.photos.indexed) _newTile(context, p, i),
              if (photos.remaining > 0)
                SizedBox.square(
                  dimension: _size,
                  child: OutlinedButton(
                    key: const Key('add-photo'),
                    style: OutlinedButton.styleFrom(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size.square(_size),
                      // 사진 칸과 같은 모양(둥근 네모)
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    onPressed: onAdd,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [const Icon(Icons.add_a_photo_outlined), Text('${photos.count}/$maxPhotos')],
                    ),
                  ),
                ),
            ],
          ),
        ),
        for (final message in failed)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(message, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
      ],
    );
  }

  Widget _newTile(BuildContext context, NewPhoto p, int i) {
    final label = '새 사진 ${i + 1}';
    final Widget? overlay = switch (p.state) {
      PhotoState.preparing => const SizedBox.square(dimension: 24, child: CircularProgressIndicator(strokeWidth: 3)),
      PhotoState.uploading => Text(
          '${(p.progress * 100).round()}%',
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
      PhotoState.failed => IconButton(
          tooltip: '$label 다시 올리기',
          style: IconButton.styleFrom(backgroundColor: Colors.white, minimumSize: const Size.square(48)),
          icon: const Icon(Icons.refresh),
          onPressed: () => photos.retry(p),
        ),
      PhotoState.uploaded => null,
    };
    return _tile(
      context,
      image: p.jpeg == null ? const ColoredBox(color: Colors.black12) : Image.memory(p.jpeg!, fit: BoxFit.cover, cacheWidth: 300),
      label: '$label${p.state == PhotoState.failed ? ' (실패)' : ''}',
      dimmed: p.state != PhotoState.uploaded,
      overlay: overlay,
      actionIcon: Icons.close,
      actionLabel: '$label 빼기',
      onAction: () => photos.remove(p),
    );
  }

  Widget _tile(
    BuildContext context, {
    required Widget image,
    required String label,
    required bool dimmed,
    required Widget? overlay,
    required IconData actionIcon,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Semantics(
        label: label,
        child: SizedBox.square(
          dimension: _size,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Stack(
              fit: StackFit.expand,
              children: [
                image,
                if (dimmed) const ColoredBox(color: Colors.black45),
                if (overlay != null) Center(child: overlay),
                // 빼기 버튼: 보이는 원은 작아도 누르는 영역은 48dp
                Positioned(
                  top: 0,
                  right: 0,
                  child: IconButton(
                    tooltip: actionLabel,
                    constraints: const BoxConstraints.tightFor(width: 48, height: 48),
                    padding: EdgeInsets.zero,
                    onPressed: onAction,
                    icon: CircleAvatar(
                      radius: 12,
                      backgroundColor: Colors.black54,
                      child: Icon(actionIcon, size: 16, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
