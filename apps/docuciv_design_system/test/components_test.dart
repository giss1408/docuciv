import 'package:docuciv_design_system/docuciv_design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) =>
      MaterialApp(theme: DocuCivTheme.light(), home: Scaffold(body: child));

  testWidgets('DocuCivStatusBadge renders its label', (tester) async {
    await tester.pumpWidget(
      wrap(const DocuCivStatusBadge(label: 'En revue', severity: DocuCivStatusSeverity.pending)),
    );
    expect(find.text('En revue'), findsOneWidget);
  });

  testWidgets('DocuCivEmptyState renders title and optional message', (tester) async {
    await tester.pumpWidget(
      wrap(
        const DocuCivEmptyState(
          icon: Icons.inbox_outlined,
          title: 'Aucune donnée',
          message: 'Revenez plus tard',
        ),
      ),
    );
    expect(find.text('Aucune donnée'), findsOneWidget);
    expect(find.text('Revenez plus tard'), findsOneWidget);
  });

  testWidgets('DocuCivSectionHeader renders title and trailing widget', (tester) async {
    await tester.pumpWidget(
      wrap(
        const DocuCivSectionHeader(
          title: 'Section',
          trailing: Icon(Icons.filter_list),
        ),
      ),
    );
    expect(find.text('Section'), findsOneWidget);
    expect(find.byIcon(Icons.filter_list), findsOneWidget);
  });

  testWidgets('DocuCivCard is tappable when onTap is provided', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      wrap(DocuCivCard(onTap: () => tapped = true, child: const Text('Card content'))),
    );
    await tester.tap(find.text('Card content'));
    expect(tapped, isTrue);
  });

  testWidgets('DocuCivTheme.dark() builds a dark ThemeData', (tester) async {
    final theme = DocuCivTheme.dark();
    expect(theme.brightness, Brightness.dark);
  });
}
