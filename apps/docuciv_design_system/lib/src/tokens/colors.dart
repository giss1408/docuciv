import 'package:flutter/material.dart';

/// Brand + semantic color tokens shared by all 3 DocuCiv apps.
///
/// Keep status colors meaning-stable across apps: a citizen sees "rejeté"
/// in the Customer App in the same red an issuer agent sees in the Admin
/// Portal — the semantics in docs/data-model.md §3 should be visually
/// legible as one system, not 3 independent color choices.
class DocuCivColors {
  DocuCivColors._();

  static const Color brandPrimary = Color(0xFF0B6E4F); // sovereign green
  static const Color brandSecondary = Color(0xFFF2994A); // warm accent

  static const Color statusPending = Color(0xFF9A6B00);
  static const Color statusInProgress = Color(0xFF1B5FAD);
  static const Color statusSuccess = Color(0xFF1E7A3E);
  static const Color statusError = Color(0xFFB3261E);
  static const Color statusNeutral = Color(0xFF5C5F66);
}
