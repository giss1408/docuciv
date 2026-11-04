import 'package:docuciv_customer/main.dart' as app;
import 'package:docuciv_ui/docuciv_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shell shows logo and switches between tabs', (tester) async {
    app.main();
    await tester.pumpAndSettle();
    expect(find.byType(DocuCivApp), findsOneWidget);
    expect(find.byType(DocuCivLogo), findsOneWidget);
    expect(find.text('Comment ça marche'), findsOneWidget);

    await tester.tap(find.text('À propos'));
    await tester.pumpAndSettle();
    expect(find.text('Notre mission'), findsOneWidget);

    await tester.tap(find.text('Mes démarches'));
    await tester.pumpAndSettle();
    expect(find.text('Aucune démarche pour le moment'), findsOneWidget);
  });

  for (final size in [const Size(320, 640), const Size(1280, 800)]) {
    testWidgets('no overflow at ${size.width}dp, text scale 2.0', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.view.reset);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      app.main();
      await tester.pumpAndSettle();
      for (final tab in ['Accueil', 'Mes démarches', 'Vérifier', 'À propos']) {
        await tester.tap(find.text(tab).first);
        await tester.pumpAndSettle();
      }
      expect(tester.takeException(), isNull);
    });
  }
}
