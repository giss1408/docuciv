import 'package:flutter/material.dart';

import '../tokens/colors.dart';
import '../tokens/spacing.dart';

/// Generic severity levels for a status pill. Screens map their own
/// domain status (e.g. `DocumentRequest.status`, docs/data-model.md §3)
/// onto one of these — this widget deliberately knows nothing about
/// DocuCiv business states, so it stays reusable across all 3 apps.
enum DocuCivStatusSeverity { pending, inProgress, success, error, neutral }

class DocuCivStatusBadge extends StatelessWidget {
  const DocuCivStatusBadge({super.key, required this.label, required this.severity});

  final String label;
  final DocuCivStatusSeverity severity;

  Color _color() {
    switch (severity) {
      case DocuCivStatusSeverity.pending:
        return DocuCivColors.statusPending;
      case DocuCivStatusSeverity.inProgress:
        return DocuCivColors.statusInProgress;
      case DocuCivStatusSeverity.success:
        return DocuCivColors.statusSuccess;
      case DocuCivStatusSeverity.error:
        return DocuCivColors.statusError;
      case DocuCivStatusSeverity.neutral:
        return DocuCivColors.statusNeutral;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _color();
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: DocuCivSpacing.sm,
        vertical: DocuCivSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: color,
              fontWeight: FontWeight.w600,
            ),
      ),
    );
  }
}
