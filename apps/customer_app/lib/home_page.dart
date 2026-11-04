import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter/material.dart';

/// Accueil: promesse + parcours en quatre étapes (docs/architecture.md §5).
class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return PageScroll(
      children: [
        Container(
          padding: const EdgeInsets.all(Space.lg),
          decoration: BoxDecoration(
            color: scheme.primaryContainer,
            borderRadius: BorderRadius.circular(Radii.lg),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Vos documents administratifs, sécurisés.',
                style: theme.textTheme.headlineMedium
                    ?.copyWith(color: scheme.onPrimaryContainer),
              ),
              const SizedBox(height: Space.sm),
              Text(
                'Demandez un document, suivez son traitement et transmettez-le en '
                'toute confiance : chaque PDF est signé et vérifiable.',
                style: theme.textTheme.bodyLarge
                    ?.copyWith(color: scheme.onPrimaryContainer),
              ),
              const SizedBox(height: Space.md),
              const Row(
                children: [
                  Icon(Icons.verified, size: 20),
                  SizedBox(width: Space.sm),
                  Flexible(child: Text('Signature numérique et QR code sur chaque document')),
                ],
              ),
            ],
          ),
        ),
        const SectionHeader('Comment ça marche'),
        const InfoCard(
          child: Column(
            children: [
              FeatureTile(
                icon: Icons.edit_note,
                title: '1. Vous faites la demande',
                body: 'Indiquez le numéro du document existant et joignez une photo '
                    'ou un scan à l\'appui.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.payments_outlined,
                title: '2. Vous payez en Mobile Money',
                body: 'Orange Money, MTN MoMo ou Moov Money, après vérification que '
                    'le document existe.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.account_balance_outlined,
                title: '3. L\'administration examine',
                body: 'Un agent contrôle votre pièce, puis émet et signe le document.',
              ),
              SizedBox(height: Space.md),
              FeatureTile(
                icon: Icons.picture_as_pdf_outlined,
                title: '4. Vous recevez votre PDF',
                body: 'Téléchargez-le et transmettez-le à l\'administration qui vous '
                    'le demande.',
              ),
            ],
          ),
        ),
        const SizedBox(height: Space.md),
      ],
    );
  }
}
