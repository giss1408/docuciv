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

  test('each app has its own accent and readable text on it', () {
    final primaries = {
      for (final seed in [docuCivSeed, docuCivAdminSeed, docuCivOwnerSeed])
        docuCivTheme(seed: seed).colorScheme.primary,
    };
    expect(primaries.length, 3);
    for (final seed in [docuCivSeed, docuCivAdminSeed, docuCivOwnerSeed]) {
      final c = docuCivTheme(seed: seed).colorScheme;
      final hi = c.primary.computeLuminance() > c.onPrimary.computeLuminance()
          ? c.primary
          : c.onPrimary;
      final lo = hi == c.primary ? c.onPrimary : c.primary;
      final ratio = (hi.computeLuminance() + 0.05) / (lo.computeLuminance() + 0.05);
      expect(ratio, greaterThanOrEqualTo(4.5)); // WCAG AA
    }
  });
}
