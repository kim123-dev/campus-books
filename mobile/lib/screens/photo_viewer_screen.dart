import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

/// 사진 전체 화면: 좌우로 넘기기, 두 손가락으로 확대(최대 4배)
class PhotoViewerScreen extends StatefulWidget {
  const PhotoViewerScreen({super.key, required this.urls, required this.initialIndex});

  final List<String> urls;
  final int initialIndex;

  @override
  State<PhotoViewerScreen> createState() => _PhotoViewerScreenState();
}

class _PhotoViewerScreenState extends State<PhotoViewerScreen> {
  late final PageController _pages = PageController(initialPage: widget.initialIndex);
  late int _index = widget.initialIndex;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text('${_index + 1} / ${widget.urls.length}'),
      ),
      body: PageView.builder(
        controller: _pages,
        itemCount: widget.urls.length,
        onPageChanged: (index) => setState(() => _index = index),
        itemBuilder: (context, index) => InteractiveViewer(
          maxScale: 4,
          child: Center(
            child: CachedNetworkImage(
              imageUrl: widget.urls[index],
              fit: BoxFit.contain,
              placeholder: (_, _) => const Center(child: CircularProgressIndicator()),
              errorWidget: (_, _, _) => const Icon(Icons.broken_image_outlined, color: Colors.white),
            ),
          ),
        ),
      ),
    );
  }
}
