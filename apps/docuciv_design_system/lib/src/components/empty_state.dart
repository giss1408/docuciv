import 'package:flutter/material.dart';

import '../tokens/spacing.dart';

/// Generic "nothing here yet" / "no results" placeholder, shared so the
/// 3 apps don't each invent their own ad hoc empty-list text widget.
class DocuCivEmptyState extends StatelessWidget {
  const DocuCivEmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(DocuCivSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(height: DocuCivSpacing.md),
            Text(
              title,
              style: theme.textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            if (message != null) ...[
              const SizedBox(height: DocuCivSpacing.xs),
              Text(
                message!,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
            ],
            if (action != null) ...[
              const SizedBox(height: DocuCivSpacing.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}
