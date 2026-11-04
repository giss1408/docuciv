import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter/material.dart';

import 'home_page.dart';

void main() => runApp(
      const DocuCivApp(
        title: 'DocuCiv',
        destinations: [
          DocuCivDestination(
            label: 'Accueil',
            icon: Icons.home_outlined,
            selectedIcon: Icons.home,
            page: HomePage(),
          ),
          DocuCivDestination(
            label: 'Mes démarches',
            icon: Icons.assignment_outlined,
            selectedIcon: Icons.assignment,
            page: EmptyState(
              icon: Icons.assignment_outlined,
              badge: 'Bientôt disponible',
              title: 'Aucune démarche pour le moment',
              message: 'Vos demandes de documents apparaîtront ici, avec le détail '
                  'de chaque étape, de la demande à la remise du PDF signé.',
            ),
          ),
          DocuCivDestination(
            label: 'Vérifier',
            icon: Icons.qr_code_scanner_outlined,
            selectedIcon: Icons.qr_code_scanner,
            page: EmptyState(
              icon: Icons.qr_code_scanner_outlined,
              badge: 'Bientôt disponible',
              title: 'Vérifier un document',
              message: 'Scannez le QR code d\'un document DocuCiv pour contrôler '
                  'son authenticité.',
            ),
          ),
          DocuCivDestination(
            label: 'À propos',
            icon: Icons.info_outline,
            selectedIcon: Icons.info,
            page: AboutPage(
              audience: 'Vos documents administratifs, sécurisés de la demande à la '
                  'vérification.',
            ),
          ),
        ],
      ),
    );
