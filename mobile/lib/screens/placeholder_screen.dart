import 'package:flutter/material.dart';

/// 아직 만들지 않은 탭. 다음 단계에서 실제 화면으로 바꾼다.
class PlaceholderScreen extends StatelessWidget {
  const PlaceholderScreen({super.key, required this.title, required this.stage});

  final String title;
  final String stage;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(child: Text('준비 중입니다 ($stage)', textAlign: TextAlign.center)),
    );
  }
}
