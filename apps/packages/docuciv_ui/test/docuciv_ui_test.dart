import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('DocuCivApp shows title and applies shared theme', (tester) async {
    await tester.pumpWidget(const DocuCivApp(title: 'Test'));
    expect(find.text('Test'), findsOneWidget);
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.theme!.colorScheme.primary, isNot(Colors.transparent));
    expect(app.theme!.useMaterial3, isTrue);
  });
}
