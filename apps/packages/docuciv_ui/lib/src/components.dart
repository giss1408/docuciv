import 'package:flutter/material.dart';

import 'tokens.dart';

/// Page défilante centrée et bornée en largeur: base commune de tous les onglets.
class PageScroll extends StatelessWidget {
  const PageScroll({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: maxContentWidth),
        child: ListView(
          padding: const EdgeInsets.all(Space.md),
          children: children,
        ),
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: Space.lg, bottom: Space.sm),
      child: Semantics(
        header: true,
        child: Text(title, style: Theme.of(context).textTheme.titleLarge),
      ),
    );
  }
}

/// Carte à bordure fine (voir `cardTheme`) avec un rembourrage standard.
class InfoCard extends StatelessWidget {
  const InfoCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      Card(child: Padding(padding: const EdgeInsets.all(Space.md), child: child));
}

/// Ligne icône + titre + texte, pour les listes d'arguments et d'étapes.
class FeatureTile extends StatelessWidget {
  const FeatureTile({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: theme.colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(Radii.sm),
          ),
          child: Icon(icon, size: 22, color: theme.colorScheme.onPrimaryContainer),
        ),
        const SizedBox(width: Space.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.titleMedium),
              const SizedBox(height: Space.xs),
              Text(
                body,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// État vide: une phrase, et une action seulement quand elle existe vraiment.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.badge,
  });

  final IconData icon;
  final String title;
  final String message;

  /// Pastille de statut (ex. "Bientôt disponible"): texte, jamais la couleur seule.
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Défilable: à fort grossissement du texte, le contenu défile au lieu de déborder.
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Padding(
                padding: const EdgeInsets.all(Space.lg),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 72,
                      height: 72,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.primaryContainer,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(icon,
                          size: 32, color: theme.colorScheme.onPrimaryContainer),
                    ),
                    const SizedBox(height: Space.md),
                    if (badge != null) ...[
                      StatusBadge(badge!),
                      const SizedBox(height: Space.sm),
                    ],
                    Text(title,
                        style: theme.textTheme.titleLarge,
                        textAlign: TextAlign.center),
                    const SizedBox(height: Space.sm),
                    Text(
                      message,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge(this.label, {super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.sm + Space.xs, vertical: Space.xs),
      decoration: BoxDecoration(
        color: theme.colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(100),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(
          color: theme.colorScheme.onSecondaryContainer,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
