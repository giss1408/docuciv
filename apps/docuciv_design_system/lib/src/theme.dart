import 'package:flutter/material.dart';

import 'tokens/colors.dart';
import 'tokens/spacing.dart';

/// Shared Material 3 theme for the 3 DocuCiv apps. Keep this the single
/// source of truth for colors/typography/component shapes so Customer
/// App, Admin Portal and Owner Backoffice stay visually consistent
/// (AGENTS.md règle 6/7) — individual screens should not override these.
class DocuCivTheme {
  DocuCivTheme._();

  static ThemeData light() => _build(Brightness.light);

  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: DocuCivColors.brandPrimary,
      brightness: brightness,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: colorScheme.surface,
      visualDensity: VisualDensity.standard,
      textTheme: _textTheme(colorScheme),
      appBarTheme: AppBarTheme(
        backgroundColor: colorScheme.surface,
        foregroundColor: colorScheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 2,
        centerTitle: false,
        titleTextStyle: _textTheme(colorScheme).titleLarge,
      ),
      cardTheme: CardTheme(
        elevation: 0,
        color: colorScheme.surfaceContainerLow,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(DocuCivRadii.lg),
          side: BorderSide(color: colorScheme.outlineVariant),
        ),
        margin: EdgeInsets.zero,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(
            horizontal: DocuCivSpacing.lg,
            vertical: DocuCivSpacing.md,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(DocuCivRadii.md),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(
            horizontal: DocuCivSpacing.lg,
            vertical: DocuCivSpacing.md,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(DocuCivRadii.md),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          padding: const EdgeInsets.symmetric(
            horizontal: DocuCivSpacing.md,
            vertical: DocuCivSpacing.sm,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(DocuCivRadii.md),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colorScheme.surfaceContainerHighest,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: DocuCivSpacing.md,
          vertical: DocuCivSpacing.md,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(DocuCivRadii.md),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(DocuCivRadii.md),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(DocuCivRadii.md),
          borderSide: BorderSide(color: colorScheme.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(DocuCivRadii.md),
          borderSide: BorderSide(color: colorScheme.error, width: 1.5),
        ),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(DocuCivRadii.pill),
        ),
        padding: const EdgeInsets.symmetric(horizontal: DocuCivSpacing.sm),
      ),
      dividerTheme: DividerThemeData(color: colorScheme.outlineVariant, space: 1),
    );
  }

  static TextTheme _textTheme(ColorScheme colorScheme) {
    return Typography.material2021(colorScheme: colorScheme).black.apply(
          fontFamily: 'Roboto',
          bodyColor: colorScheme.onSurface,
          displayColor: colorScheme.onSurface,
        );
  }
}
