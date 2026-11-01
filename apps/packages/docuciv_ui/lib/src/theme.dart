import 'package:flutter/material.dart';

/// Couleur de marque unique; les trois apps en dérivent leur ColorScheme.
const Color docuCivSeed = Color(0xFF1B6B4A);

ThemeData docuCivTheme({Brightness brightness = Brightness.light}) {
  final scheme =
      ColorScheme.fromSeed(seedColor: docuCivSeed, brightness: brightness);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(),
    ),
  );
}
