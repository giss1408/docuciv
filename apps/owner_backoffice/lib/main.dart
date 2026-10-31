import 'package:docuciv_design_system/docuciv_design_system.dart';
import 'package:flutter/material.dart';

void main() {
  runApp(const OwnerBackofficeApp());
}

/// Équipe DocuCiv uniquement — accès transverse à tous les tenants, jamais
/// exposé aux autres apps (AGENTS.md règle 7, docs/architecture.md §4).
/// SSO + MFA obligatoires (non implémentés dans ce scaffold Phase 0).
class OwnerBackofficeApp extends StatelessWidget {
  const OwnerBackofficeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DocuCiv — Owner Backoffice',
      theme: DocuCivTheme.light(),
      darkTheme: DocuCivTheme.dark(),
      home: const TenantsScreen(),
    );
  }
}

class TenantsScreen extends StatelessWidget {
  const TenantsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Administrations (tenants)')),
      body: const DocuCivEmptyState(
        icon: Icons.apartment_outlined,
        title: 'Aucun tenant',
        message: 'Les administrations partenaires apparaîtront ici une fois onboardées.',
      ),
    );
  }
}
