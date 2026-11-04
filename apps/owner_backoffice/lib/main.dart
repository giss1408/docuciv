import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter/material.dart';

void main() => runApp(
      const DocuCivApp(
        title: 'DocuCiv Owner',
        seed: docuCivOwnerSeed,
        logoSuffix: 'OWNER',
        destinations: [
          DocuCivDestination(
            label: 'Administrations',
            icon: Icons.apartment_outlined,
            selectedIcon: Icons.apartment,
            page: EmptyState(
              icon: Icons.apartment_outlined,
              badge: 'Bientôt disponible',
              title: 'Administrations',
              message: 'La gestion des administrations, de leurs abonnements et de '
                  'leur usage apparaîtra ici.',
            ),
          ),
          DocuCivDestination(
            label: 'Réclamations',
            icon: Icons.support_agent_outlined,
            selectedIcon: Icons.support_agent,
            page: EmptyState(
              icon: Icons.support_agent_outlined,
              badge: 'Bientôt disponible',
              title: 'Réclamations transverses',
              message: 'Les réclamations qui concernent la plateforme elle-même '
                  'apparaîtront ici.',
            ),
          ),
          DocuCivDestination(
            label: 'À propos',
            icon: Icons.info_outline,
            selectedIcon: Icons.info,
            page: AboutPage(
              audience: 'Le back-office de l\'équipe DocuCiv : supervision de la '
                  'plateforme.',
            ),
          ),
        ],
      ),
    );
