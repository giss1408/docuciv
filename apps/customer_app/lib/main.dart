import 'package:docuciv_design_system/docuciv_design_system.dart';
import 'package:flutter/material.dart';

void main() {
  runApp(const CustomerApp());
}

class CustomerApp extends StatelessWidget {
  const CustomerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DocuCiv',
      theme: DocuCivTheme.light(),
      darkTheme: DocuCivTheme.dark(),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('DocuCiv')),
      body: const SafeArea(
        child: Padding(
          padding: EdgeInsets.all(DocuCivSpacing.md),
          child: DocuCivSectionHeader(title: 'Mes démarches'),
        ),
      ),
    );
  }
}
