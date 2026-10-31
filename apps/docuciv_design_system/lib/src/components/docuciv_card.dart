import 'package:flutter/material.dart';

import '../tokens/spacing.dart';

/// Thin wrapper over [Card] that applies the shared padding so every
/// screen doesn't re-decide its own card inset.
class DocuCivCard extends StatelessWidget {
  const DocuCivCard({super.key, required this.child, this.onTap, this.padding});

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: padding ?? const EdgeInsets.all(DocuCivSpacing.md),
      child: child,
    );

    return Card(
      child: onTap == null
          ? content
          : InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(16),
              child: content,
            ),
    );
  }
}
