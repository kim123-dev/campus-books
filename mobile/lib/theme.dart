import 'package:flutter/material.dart';

const brandColor = Color(0xFF5B3FD6);

/// 누르는 곳은 최소 48dp (웹의 44px 기준을 안드로이드 권장값으로).
const minTouch = Size(64, 48);

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: brandColor).copyWith(primary: brandColor);
  return ThemeData(
    colorScheme: scheme,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(minimumSize: minTouch)),
    outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(minimumSize: minTouch)),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(minimumSize: minTouch)),
    inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
  );
}
