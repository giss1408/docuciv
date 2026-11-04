import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:docuciv_owner/main.dart' as app;

void main() {
  testWidgets('shell shows logo and an About tab', (tester) async {
    app.main();
    await tester.pumpAndSettle();
    expect(find.byType(DocuCivApp), findsOneWidget);
    expect(find.byType(DocuCivLogo), findsOneWidget);
    await tester.tap(find.text('À propos'));
    await tester.pumpAndSettle();
    expect(find.text('Notre mission'), findsOneWidget);
  });
}
