import 'package:flutter/material.dart';

import 'tokens.dart';

/// Une couleur d'accent par app (même design system, identité distincte): vert pour le
/// citoyen, bleu pour l'Admin Portal, orange pour l'Owner Backoffice. `ColorScheme.fromSeed`
/// garantit le contraste du texte sur l'accent.
const Color docuCivSeed = Color(0xFF1B6B4A); // Customer: vert
const Color docuCivAdminSeed = Color(0xFF1D4ED8); // Admin Portal: bleu
const Color docuCivOwnerSeed = Color(0xFFC2410C); // Owner Backoffice: orange

ThemeData docuCivTheme({
  Brightness brightness = Brightness.light,
  Color seed = docuCivSeed,
}) {
  final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness);
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final text = base.textTheme;
  final shape =
      RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md));

  return base.copyWith(
    scaffoldBackgroundColor: scheme.surface,
    textTheme: text.copyWith(
      labelSmall: text.labelSmall?.copyWith(fontSize: 12, fontWeight: FontWeight.w500),
      bodyMedium: text.bodyMedium?.copyWith(fontSize: 14, height: 1.5),
      bodyLarge: text.bodyLarge?.copyWith(fontSize: 16, height: 1.5),
      titleMedium: text.titleMedium?.copyWith(fontSize: 16, fontWeight: FontWeight.w600),
      titleLarge: text.titleLarge?.copyWith(fontSize: 22, fontWeight: FontWeight.w600),
      headlineMedium: text.headlineMedium
          ?.copyWith(fontSize: 30, fontWeight: FontWeight.w700, height: 1.2),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      shape: Border(bottom: BorderSide(color: scheme.outlineVariant)),
    ),
    // Carte: surface, bordure 1px, pas d'élévation.
    cardTheme: CardTheme(
      color: scheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Radii.md),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      indicatorColor: scheme.primaryContainer,
      labelTextStyle: WidgetStatePropertyAll(
        text.labelSmall?.copyWith(fontWeight: FontWeight.w600),
      ),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: scheme.surface,
      indicatorColor: scheme.primaryContainer,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: shape,
        textStyle: text.labelLarge?.copyWith(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: shape,
        side: BorderSide(color: scheme.outline),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerLowest,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Radii.md),
        borderSide: BorderSide(color: scheme.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Radii.md),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Radii.md),
        borderSide: BorderSide(color: scheme.primary, width: 2),
      ),
    ),
  );
}
