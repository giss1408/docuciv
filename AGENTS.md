# AGENTS.md — DocuCiv

Instructions pour tout agent IA (Claude Code ou autre) travaillant sur ce dépôt.

## Contexte du projet

DocuCiv est une plateforme SaaS de sécurisation des documents administratifs en Côte d'Ivoire. Elle relie trois acteurs :
- **Citoyen/Entreprise** : fournit l'identifiant du document existant + une photo/scan à l'appui, demande et reçoit le document final au format PDF
- **Administration émettrice** : examine la pièce justificative, produit et signe numériquement le document PDF
- **Administration requérante** : reçoit le PDF transmis par le citoyen et vérifie son authenticité

Parcours clé : citoyen (ID du document + photo) → paiement → revue par l'administration émettrice → émission PDF signé → retour au citoyen → transmission par le citoyen à l'administration requérante → vérification. Détail complet dans `docs/architecture.md` §5.

Vision complète : voir [`concept.md`](./concept.md).
Documentation détaillée : voir [`docs/`](./docs).

## Documents de référence (à lire avant toute implémentation)

| Document | Contenu |
|---|---|
| [`docs/requirements.md`](./docs/requirements.md) | Exigences fonctionnelles et non fonctionnelles, user stories par acteur |
| [`docs/architecture.md`](./docs/architecture.md) | Architecture technique, services, stack, flux de données |
| [`docs/data-model.md`](./docs/data-model.md) | Modèle de données (entités, relations, états) |
| [`docs/api-spec.md`](./docs/api-spec.md) | Contrats d'API entre services et avec les clients |
| [`docs/security.md`](./docs/security.md) | Sécurité in-depth : modèle de menaces STRIDE, OWASP API Top 10, hiérarchie de clés, isolation multi-tenant (BOLA), conformité |
| [`docs/roadmap.md`](./docs/roadmap.md) | Phases MVP, découpage en tâches livrables |
| [`docs/workflow.md`](./docs/workflow.md) | Ordre de test (smoke tests puis e2e en fin de phase), modèle de branches (`feature/* → integration → main`), pipelines Codemagic (Google Play / App Store) |
| [`docs/notifications.md`](./docs/notifications.md) | Message exact à envoyer à chaque transition d'état (succès/échec), contrôle d'existence avant paiement, délais et relance, suivi de statut, réclamations |

## Règles de travail

1. **Ne pas casser l'interopérabilité** : tout changement de schéma de document ou d'API doit rester compatible avec les trois rôles (citoyen, admin émettrice, admin requérante).
2. **Sécurité par défaut** : toute route touchant à la signature, au paiement ou à la vérification doit être traitée comme sensible — pas de raccourci, pas de désactivation de contrôle sans accord explicite.
3. **Conformité locale** : respecter la loi ivoirienne sur la cryptographie/signature électronique et les contraintes RGPD/CNIL-CI (voir `docs/security.md`).
4. **Mobile Money** : les intégrations Orange Money / MTN MoMo / Moov Money sont des intégrations externes réelles (paiement) — ne jamais simuler silencieusement un paiement réussi en dehors des tests.
5. **MVP-first** : respecter le découpage de `docs/roadmap.md`. Ne pas anticiper des fonctionnalités hors MVP sans qu'on le demande.
6. **Stack imposée** : backend **Python/FastAPI** (PostgreSQL + Redis, Celery pour l'async, ECC/HSM pour la signature) ; clients **Flutter** pour les 3 apps (Customer iOS/Android/Web, Admin Portal Web, Owner Backoffice Web). Ne pas introduire une autre techno backend ou un autre framework client sans accord explicite — voir `docs/architecture.md`.
7. **3 apps distinctes, 1 backend** : Customer App (citoyens/entreprises), Admin Portal (agents des administrations émettrices/requérantes, par tenant), Owner Backoffice (équipe DocuCiv, gestion des tenants/facturation/supervision). Ne jamais mélanger les privilèges "owner" dans l'Admin Portal ou le Customer App.
8. **Multi-tenant par construction** : toute nouvelle table métier doit porter un `tenant_id`, être protégée par une policy Row-Level Security PostgreSQL (jamais seulement un `WHERE` applicatif), et tout nouvel endpoint doit avoir un test automatisé d'accès croisé entre deux tenants factices (BOLA) avant merge — voir `docs/data-model.md` §4 et `docs/security.md` §2/§4. Pas de requête inter-tenant sans passer par le rôle Owner, et jamais sans entrée dans `PlatformAuditLog` avec justification.
9. **Production grade** : toute fonctionnalité livrée doit inclure tests automatisés, logs structurés (sans PII en clair), et respecter les exigences de `docs/architecture.md` §6 (HA, observabilité, CI/CD) — pas de "ça marche en local" comme critère de complétion.
10. **Clés de signature** : ne jamais faire transiter ou générer une clé privée côté client (Flutter) ; toute opération de signature passe par le HSM/KMS via le service Signature. Respecter la hiérarchie de clés (`docs/architecture.md` §4bis, `docs/security.md` §3) : une clé retirée/compromise n'est jamais supprimée, seulement marquée `retired`/`compromised`.
11. **Format de sortie unique** : tout document émis est un **PDF** signé avec QR code intégré. Pas d'autre format de sortie sans accord explicite.
12. **La pièce justificative n'est pas une preuve cryptographique** : la photo/scan fournie par le citoyen (`SourceEvidence`) sert uniquement à la revue humaine par l'agent émetteur avant émission — ne jamais la traiter comme un élément d'authentification côté vérification. Elle doit être uploadée directement vers S3 (jamais en base64 dans l'API), validée (type MIME réel, taille, antivirus) et n'est jamais visible par une administration requérante.
13. **Transmission (`DocumentShare`) ≠ preuve (`qr_code_token`)** : un jeton de partage est toujours distinct du jeton QR du document, à usage/durée limités et révocable par le citoyen. Révoquer un partage ne doit jamais invalider le document lui-même.
14. **Ordre de test** : pour chaque tâche, implémenter puis écrire/lancer des **smoke tests ciblés** immédiatement (feedback rapide, pas de dépendance à l'environnement complet). Ne jamais écrire ni exécuter la suite **end-to-end** en cours de tâche — elle ne s'exécute qu'en fin de phase de `docs/roadmap.md`, ou automatiquement sur la branche `integration`. Voir `docs/workflow.md` §1.
15. **Branches** : tout travail part d'une `feature/*`, merge vers `integration` (staging, auto-déployé, où tournent les e2e), puis promotion validée vers `main` (production, déclenche les releases stores). Jamais de commit direct sur `integration` ou `main`. Voir `docs/workflow.md` §2.
16. **Releases mobiles** : les builds/soumissions Google Play et App Store passent exclusivement par **Codemagic**, déclenchés sur `main` (soumission store) ou `integration` (distribution interne uniquement). La promotion finale en production dans Play Console/App Store Connect reste une validation humaine. Voir `docs/workflow.md` §5.
17. **Notifier à chaque étape, succès et échec** : toute transition de `DocumentRequest` (ou de `SourceEvidence`/`Transaction`) doit déclencher la notification correspondante définie dans `docs/notifications.md` §2 — jamais seulement la notification de succès final. Ne pas demander de paiement avant confirmation que le `reference_document_id` existe (`docs/notifications.md` §3).
18. **Statut et réclamations** : toute demande doit rester consultable à tout moment (`GET /requests/{id}` avec timeline), et un citoyen doit toujours pouvoir déposer une réclamation. Ne pas construire un flux de notification sans le flux de réclamation associé — voir `docs/notifications.md` §6.

## État du dépôt

Ce dépôt ne contient aujourd'hui que la documentation de concept et de spécification (`concept.md`, `docs/`). Aucun code applicatif n'existe encore — toute implémentation démarre de zéro et doit suivre la Phase 1 de la roadmap (Design & UX) avant le code.
