import 'package:flutter/material.dart';

import 'shell.dart';
import 'theme.dart';

/// Coquille commune: thème partagé + navigation par onglets. Chaque app fournit son titre et
/// ses onglets (`destinations`), ou une page libre (`home`).
class DocuCivApp extends StatelessWidget {
  const DocuCivApp({
    super.key,
    required this.title,
    this.home,
    this.destinations,
    this.logoSuffix,
    this.seed = docuCivSeed,
  });

  final String title;
  final Widget? home;
  final List<DocuCivDestination>? destinations;
  final String? logoSuffix;

  /// Couleur d'accent de l'app (voir `docuCivSeed`, `docuCivAdminSeed`, `docuCivOwnerSeed`).
  final Color seed;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: title,
      debugShowCheckedModeBanner: false,
      theme: docuCivTheme(seed: seed),
      darkTheme: docuCivTheme(brightness: Brightness.dark, seed: seed),
      home: home ??
          (destinations != null
              ? DocuCivShell(destinations: destinations!, logoSuffix: logoSuffix)
              : Scaffold(appBar: AppBar(title: Text(title)))),
    );
  }
}
