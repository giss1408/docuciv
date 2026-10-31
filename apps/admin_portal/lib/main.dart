import 'package:docuciv_design_system/docuciv_design_system.dart';
import 'package:flutter/material.dart';

void main() {
  runApp(const AdminPortalApp());
}

/// Agents des administrations émettrices/requérantes, scoped à un seul
/// tenant par session — jamais de privilèges Owner ici (AGENTS.md règle 7).
class AdminPortalApp extends StatelessWidget {
  const AdminPortalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DocuCiv — Admin Portal',
      theme: DocuCivTheme.light(),
      darkTheme: DocuCivTheme.dark(),
      home: const RequestQueueScreen(),
    );
  }
}

class RequestQueueScreen extends StatelessWidget {
  const RequestQueueScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('File de demandes')),
      body: const DocuCivEmptyState(
        icon: Icons.fact_check_outlined,
        title: 'Aucune demande en revue',
        message: 'Les nouvelles demandes apparaîtront ici dès qu\'un citoyen en soumet une.',
      ),
    );
  }
}
