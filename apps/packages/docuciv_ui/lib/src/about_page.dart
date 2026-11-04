import 'package:flutter/material.dart';

import 'components.dart';
import 'logo.dart';
import 'tokens.dart';

/// Onglet « À propos », commun aux trois apps. [audience] adapte l'accroche au public.
class AboutPage extends StatelessWidget {
  const AboutPage({super.key, required this.audience, this.version = '0.1.0'});

  final String audience;
  final String version;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PageScroll(
      children: [
        const SizedBox(height: Space.md),
        const Center(child: DocuCivMark(size: 88)),
        const SizedBox(height: Space.md),
        Text('DocuCiv',
            textAlign: TextAlign.center, style: theme.textTheme.headlineMedium),
        const SizedBox(height: Space.sm),
        Text(
          audience,
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyLarge
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SectionHeader('Notre mission'),
        const InfoCard(
          child: Text(
            'Rendre les documents administratifs de Côte d\'Ivoire simples à obtenir '
            'et impossibles à falsifier : chaque document est émis par l\'administration '
            'concernée, signé numériquement et vérifiable en quelques secondes.',
          ),
        ),
        const SectionHeader('Trois acteurs, une chaîne de confiance'),
        const InfoCard(
          child: Column(
            children: [
              FeatureTile(
                icon: Icons.person_outline,
                title: 'Citoyens et entreprises',
                body: 'Demandent leur document en ligne, suivent chaque étape et '
                    'le transmettent en toute sécurité.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.account_balance_outlined,
                title: 'Administrations émettrices',
                body: 'Examinent la demande, produisent le document et le signent '
                    'numériquement.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.fact_check_outlined,
                title: 'Administrations requérantes',
                body: 'Reçoivent le document et en vérifient l\'authenticité '
                    'instantanément.',
              ),
            ],
          ),
        ),
        const SectionHeader('Nos engagements'),
        const InfoCard(
          child: Column(
            children: [
              FeatureTile(
                icon: Icons.verified_outlined,
                title: 'Un seul format : le PDF signé',
                body: 'Chaque document porte une signature numérique et un QR code '
                    'de vérification.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.lock_outline,
                title: 'Vos pièces restent confidentielles',
                body: 'La pièce justificative n\'est vue que par l\'administration '
                    'émettrice, jamais par celle qui vous demande le document.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.wifi_off_outlined,
                title: 'Vérification même sans réseau',
                body: 'Les agents peuvent contrôler un document hors connexion.',
              ),
            ],
          ),
        ),
        const SizedBox(height: Space.lg),
        Center(
          child: Text(
            'Version $version',
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
        const SizedBox(height: Space.md),
      ],
    );
  }
}
