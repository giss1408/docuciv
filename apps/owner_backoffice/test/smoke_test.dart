import 'package:docuciv_owner/main.dart' as app;
import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app builds with shared theme', (tester) async {
    app.main();
    await tester.pump();
    expect(find.text('DocuCiv Owner'), findsOneWidget);
    expect(find.byType(DocuCivApp), findsOneWidget);
  });
}
