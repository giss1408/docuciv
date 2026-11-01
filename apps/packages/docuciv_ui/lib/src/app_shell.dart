import 'package:flutter/material.dart';

import 'theme.dart';

/// Coquille commune: thème partagé + page d'accueil. Chaque app fournit son titre et sa page.
class DocuCivApp extends StatelessWidget {
  const DocuCivApp({super.key, required this.title, this.home});

  final String title;
  final Widget? home;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: title,
      debugShowCheckedModeBanner: false,
      theme: docuCivTheme(),
      darkTheme: docuCivTheme(brightness: Brightness.dark),
      home: home ?? Scaffold(appBar: AppBar(title: Text(title))),
    );
  }
}
