import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter/material.dart';

void main() => runApp(
      const DocuCivApp(
        title: 'DocuCiv Admin',
        seed: docuCivAdminSeed,
        logoSuffix: 'ADMIN',
        destinations: [
          DocuCivDestination(
            label: 'Demandes',
            icon: Icons.inbox_outlined,
            selectedIcon: Icons.inbox,
            page: EmptyState(
              icon: Icons.inbox_outlined,
              badge: 'Bientôt disponible',
              title: 'File de revue',
              message: 'Les demandes à examiner, avec la pièce justificative, '
                  'apparaîtront ici.',
            ),
          ),
          DocuCivDestination(
            label: 'Réclamations',
            icon: Icons.support_agent_outlined,
            selectedIcon: Icons.support_agent,
            page: EmptyState(
              icon: Icons.support_agent_outlined,
              badge: 'Bientôt disponible',
              title: 'Réclamations',
              message: 'Les réclamations des citoyens, classées par échéance de '
                  'réponse, apparaîtront ici.',
            ),
          ),
          DocuCivDestination(
            label: 'À propos',
            icon: Icons.info_outline,
            selectedIcon: Icons.info,
            page: AboutPage(
              audience: 'Le portail des agents des administrations émettrices et '
                  'requérantes.',
            ),
          ),
        ],
      ),
    );
