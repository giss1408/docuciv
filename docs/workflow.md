# Workflow de développement & CI/CD — DocuCiv

Ce document fixe la méthode de travail pour tout agent IA ou humain implémentant DocuCiv : ordre des tests, modèle de branches, et pipelines de build/déploiement (backend + stores mobiles via Codemagic).

## 1. Ordre de test par fonctionnalité

Pour chaque tâche/fonctionnalité livrée (un endpoint, un écran, un flux) :

1. **Implémenter** le code (backend et/ou Flutter) pour la tâche.
2. **Smoke tests ciblés, immédiatement** : tests unitaires/d'intégration légers et rapides sur ce qui vient d'être écrit (un endpoint répond avec le bon statut/schéma, un écran se construit sans crash, une transition d'état se produit correctement). Objectif : feedback en secondes, pas en minutes — pas de dépendance à l'environnement complet (DB réelle, autres services, apps mobiles).
3. **Passer à la tâche suivante** en répétant 1-2, jusqu'à ce que le périmètre de la phase/roadmap soit couvert.
4. **Tests end-to-end (e2e) seulement à la fin** de la phase ou avant une mise en intégration/production : parcours complets multi-services (ex. demande → paiement → revue → émission PDF → partage → vérification), avec l'environnement réel ou quasi-réel (DB, S3/MinIO, mock des opérateurs Mobile Money).

**Pourquoi** : les e2e sont lents, fragiles aux détails d'environnement et coûteux à maintenir si on les lance à chaque petit changement — ils valident l'intégration finale, pas l'unité de travail. Les lancer en continu ralentit l'itération sans ajouter de signal avant que les pièces soient toutes en place.

**Règle pour l'agent** : ne pas lancer/écrire la suite e2e en même temps que chaque petite fonctionnalité. Un backlog de scénarios e2e peut être rédigé au fur et à mesure (liste de parcours à couvrir), mais leur **exécution** n'intervient qu'en fin de phase (voir `roadmap.md`, Phase 5) ou juste avant un merge vers `integration`/`main` (voir §2).

## 2. Modèle de branches

```
feature/*  ──PR──▶  integration  ──promotion──▶  main
(dev local)         (staging, auto-déployé)      (production, releases stores)
```

- **`feature/*`** : une branche par tâche. Smoke tests obligatoires avant ouverture de PR. Pas d'e2e requis à ce stade.
- **`integration`** : branche de staging. Toute PR mergée ici déclenche :
  - build + smoke tests déjà validés en PR (ne sont pas rejoués à l'identique, mais la CI de la branche rejoue l'ensemble des tests unitaires/d'intégration du repo pour détecter les régressions croisées)
  - déploiement automatique vers l'environnement **staging** (backend) et build de pré-production des 3 apps Flutter
  - **c'est ici que les tests e2e s'exécutent** (voir §1), contre l'environnement staging
- **`main`** : branche de production. Ne reçoit que des promotions depuis `integration`, et seulement si :
  - tous les tests e2e sont au vert sur `integration`
  - revue/validation explicite (pas de merge automatique de `integration` vers `main`)
  - Un merge vers `main` déclenche le déploiement backend en production **et** les pipelines Codemagic de soumission aux stores (§3).
- Pas de commit direct sur `integration` ou `main` : tout passe par PR, y compris la promotion `integration → main`.
- Hotfix critique en production : branche `hotfix/*` depuis `main`, smoke tests obligatoires, puis merge vers `main` **et** `integration` (pour ne jamais diverger), avec les mêmes gates (e2e rejoués avant le merge vers `main` si le correctif touche un parcours critique).

## 3. Environnements associés

| Branche | Environnement | Backend | Apps Flutter |
|---|---|---|---|
| `feature/*` | local/dev | local (Docker Compose) | émulateurs/simulateurs, builds debug |
| `integration` | staging | déployé auto sur staging, secrets staging (voir `security.md` §10) | builds internes (Firebase App Distribution / TestFlight interne, pas de soumission store) |
| `main` | production | déployé en production (canary/blue-green, voir `architecture.md` §6) | soumission Codemagic vers Google Play et App Store (§4) |

## 4. CI/CD — Backend (Python/FastAPI)

Pipeline (GitHub Actions ou GitLab CI, voir `architecture.md` §1) sur chaque push/PR :
1. Lint + type checking (ruff/mypy)
2. Tests unitaires + smoke tests d'intégration (DB de test éphémère)
3. Scan de dépendances (SCA) et scan de secrets — bloquant sur critique/high (voir `security.md` §10)
4. Build image Docker, scan de l'image (Trivy/Grype)
5. Sur push vers `integration` : déploiement staging + exécution de la suite e2e
6. Sur push vers `main` : déploiement production (canary/blue-green)

## 5. CI/CD — Apps Flutter (mobile/web) via Codemagic

Un `codemagic.yaml` par app (Customer, Admin Portal, Owner Backoffice) à la racine de chaque module Flutter, ou un `codemagic.yaml` unique avec un workflow par app si monorepo.

### Workflow commun à chaque app
1. `flutter pub get`, analyse statique (`flutter analyze`), tests unitaires/widget (smoke tests Flutter — voir §1)
2. Build par plateforme :
   - **Android** : `flutter build appbundle --release` (signature via keystore géré par Codemagic, jamais commité) — avec `--obfuscate --split-debug-info` en production (voir `security.md` §8)
   - **iOS** : `flutter build ipa --release` (signature automatique Codemagic via App Store Connect API key, profils de provisioning gérés par Codemagic)
   - **Web** (Admin Portal, Owner Backoffice) : `flutter build web --release`, déploiement vers l'hébergement statique (voir `architecture.md`)

### Déclenchement par branche
- **`integration`** : build + distribution interne uniquement
  - Android → Firebase App Distribution (ou piste interne Google Play)
  - iOS → TestFlight (groupe de testeurs internes)
  - Pas de soumission aux stores publics depuis cette branche.
- **`main`** : build + **soumission store**
  - Android → publication sur **Google Play Console** (piste `internal`/`beta` configurable, promotion vers `production` reste une action humaine explicite dans Play Console — Codemagic ne force jamais le passage en production sans validation)
  - iOS → soumission à **App Store Connect** (TestFlight externe ou soumission à revue Apple selon la configuration), publication finale sur l'App Store également soumise à validation humaine dans App Store Connect.

### Secrets Codemagic
- Keystore Android, clé API App Store Connect, certificats iOS : stockés dans le coffre de variables d'environnement chiffrées de Codemagic, jamais dans le repo.
- Variables d'environnement par app/branche (ex. URL de l'API backend : staging pour `integration`, production pour `main`), pour que le même code pointe vers le bon environnement selon la branche buildée.

### Exemple de structure `codemagic.yaml` (Customer App)

```yaml
workflows:
  customer-integration:
    name: Customer App - Integration (internal distribution)
    environment:
      flutter: stable
      groups:
        - google_play_internal
        - app_store_connect
    triggering:
      events: [push]
      branch_patterns:
        - pattern: integration
    scripts:
      - flutter pub get
      - flutter analyze
      - flutter test
      - flutter build appbundle --release
      - flutter build ipa --release --export-options-plist=/Users/builder/export_options.plist
    publishing:
      firebase_app_distribution:
        android:
          groups: [internal-testers]
      app_store_connect:
        auth: integration

  customer-production:
    name: Customer App - Production (store submission)
    environment:
      flutter: stable
      groups:
        - google_play_production
        - app_store_connect
    triggering:
      events: [push]
      branch_patterns:
        - pattern: main
    scripts:
      - flutter pub get
      - flutter analyze
      - flutter test
      - flutter build appbundle --release --obfuscate --split-debug-info=build/symbols
      - flutter build ipa --release --obfuscate --split-debug-info=build/symbols
    publishing:
      google_play:
        track: internal   # promotion vers production = action humaine dans Play Console
        credentials: $GOOGLE_PLAY_SERVICE_ACCOUNT_CREDENTIALS
      app_store_connect:
        auth: production
        submit_to_testflight: true
```

(Admin Portal et Owner Backoffice suivent le même schéma pour leurs builds Web ; pas de workflow de soumission store pour eux puisqu'ils ne sont pas distribués via Google Play/App Store.)

## 6. Résumé des règles pour l'agent

- Implémenter petit, tester petit (smoke tests), avancer — ne pas bloquer sur l'e2e à chaque étape.
- Les e2e s'exécutent à la fin d'une phase de la roadmap, ou automatiquement sur la branche `integration`.
- Toujours passer par `feature/* → integration → main`, jamais de commit direct sur `integration`/`main`.
- Une soumission aux stores (Google Play, App Store) ne part que de `main`, jamais de `integration` ou d'une feature branch.
- La promotion finale en production dans Play Console/App Store Connect reste une validation humaine, même si le build/upload est automatisé par Codemagic.
