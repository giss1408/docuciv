import 'package:flutter_test/flutter_test.dart';
import 'package:owner_backoffice/main.dart';

void main() {
  testWidgets('TenantsScreen builds without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const OwnerBackofficeApp());
    expect(find.text('Administrations (tenants)'), findsOneWidget);
  });
}
