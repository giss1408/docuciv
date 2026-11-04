/// Espacements (grille de 8, 4 pour les paires serrées) et rayons: jamais de valeur en dur.
abstract final class Space {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;
}

abstract final class Radii {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 20;
}

/// Largeur à partir de laquelle la navigation passe en rail latéral (apps desktop/web).
const double wideBreakpoint = 840;

/// Largeur maximale du contenu sur grand écran.
const double maxContentWidth = 1000;
