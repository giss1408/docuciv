import 'package:flutter/material.dart';

import 'tokens.dart';

/// Marque DocuCiv: un document à coin plié frappé d'un sceau de validation.
/// Dessinée en vectoriel (aucun asset) pour rester nette à toutes les tailles et en thème sombre.
class DocuCivMark extends StatelessWidget {
  const DocuCivMark({super.key, this.size = 40});

  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      label: 'Logo DocuCiv',
      image: true,
      child: ExcludeSemantics(
        child: CustomPaint(
          size: Size.square(size),
          painter: _MarkPainter(tile: scheme.primary, paper: scheme.onPrimary),
        ),
      ),
    );
  }
}

class _MarkPainter extends CustomPainter {
  _MarkPainter({required this.tile, required this.paper});

  final Color tile;
  final Color paper;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width;
    Offset p(double x, double y) => Offset(x * s, y * s);

    canvas.drawRRect(
      RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(s * 0.26)),
      Paint()..color = tile,
    );

    final sheet = Path()
      ..moveTo(p(.30, .20).dx, p(.30, .20).dy)
      ..lineTo(p(.56, .20).dx, p(.56, .20).dy)
      ..lineTo(p(.70, .34).dx, p(.70, .34).dy)
      ..lineTo(p(.70, .80).dx, p(.70, .80).dy)
      ..lineTo(p(.30, .80).dx, p(.30, .80).dy)
      ..close();
    canvas.drawPath(sheet, Paint()..color = paper);

    final fold = Path()
      ..moveTo(p(.56, .20).dx, p(.56, .20).dy)
      ..lineTo(p(.56, .34).dx, p(.56, .34).dy)
      ..lineTo(p(.70, .34).dx, p(.70, .34).dy)
      ..close();
    canvas.drawPath(fold, Paint()..color = tile.withOpacity(.35));

    final line = Paint()
      ..color = tile.withOpacity(.35)
      ..strokeWidth = s * 0.04
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(p(.37, .46), p(.52, .46), line);
    canvas.drawLine(p(.37, .55), p(.48, .55), line);

    // Sceau: disque plein cerclé de la couleur de la tuile pour le détacher de la feuille.
    final seal = p(.66, .72);
    canvas.drawCircle(seal, s * 0.19, Paint()..color = tile);
    canvas.drawCircle(seal, s * 0.15, Paint()..color = paper);
    canvas.drawCircle(seal, s * 0.12, Paint()..color = tile);
    final check = Path()
      ..moveTo(p(.60, .72).dx, p(.60, .72).dy)
      ..lineTo(p(.65, .77).dx, p(.65, .77).dy)
      ..lineTo(p(.73, .67).dx, p(.73, .67).dy);
    canvas.drawPath(
      check,
      Paint()
        ..color = paper
        ..style = PaintingStyle.stroke
        ..strokeWidth = s * 0.04
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_MarkPainter old) => old.tile != tile || old.paper != paper;
}

/// Marque + nom. `suffix` distingue les apps de staff ("Admin", "Owner").
class DocuCivLogo extends StatelessWidget {
  const DocuCivLogo({super.key, this.size = 36, this.suffix});

  final double size;
  final String? suffix;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final style = theme.textTheme.titleLarge?.copyWith(
      fontSize: size * 0.56,
      fontWeight: FontWeight.w700,
      letterSpacing: -0.3,
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        DocuCivMark(size: size),
        const SizedBox(width: Space.sm + Space.xs),
        Flexible(
          child: Text.rich(
            TextSpan(children: [
              TextSpan(text: 'Docu', style: style),
              TextSpan(
                text: 'Civ',
                style: style?.copyWith(color: theme.colorScheme.primary),
              ),
              if (suffix != null)
                TextSpan(
                  text: '  $suffix',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.4,
                  ),
                ),
            ]),
            overflow: TextOverflow.ellipsis,
            maxLines: 1,
          ),
        ),
      ],
    );
  }
}
