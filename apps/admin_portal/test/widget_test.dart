import 'package:admin_portal/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('RequestQueueScreen builds without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const AdminPortalApp());
    expect(find.text('File de demandes'), findsOneWidget);
  });
}
