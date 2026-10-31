import 'package:flutter/material.dart';

/// Shared theme for the 3 DocuCiv apps. Keep this the single source of
/// truth for colors/typography so Customer App, Admin Portal and Owner
/// Backoffice stay visually consistent (AGENTS.md règle 6/7).
class DocuCivTheme {
  static const Color primary = Color(0xFF0B6E4F);
  static const Color secondary = Color(0xFFF2994A);

  static ThemeData light() {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primary,
        brightness: Brightness.light,
      ),
    );
  }
}
