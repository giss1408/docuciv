import 'package:customer_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('HomeScreen builds without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const CustomerApp());
    expect(find.text('DocuCiv'), findsWidgets);
    expect(find.text('Mes démarches'), findsOneWidget);
  });
}
