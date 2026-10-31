import 'package:flutter/material.dart';

import '../tokens/spacing.dart';

/// Shared section title row (optionally with a trailing action), so list
/// screens across the 3 apps read as one visual system.
class DocuCivSectionHeader extends StatelessWidget {
  const DocuCivSectionHeader({super.key, required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: DocuCivSpacing.sm),
      child: Row(
        children: [
          Expanded(
            child: Text(title, style: Theme.of(context).textTheme.titleMedium),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
