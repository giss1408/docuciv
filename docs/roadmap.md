# Roadmap MVP — DocuCiv

Stack : backend Python/FastAPI, 3 apps Flutter (Customer iOS/Android/Web, Admin Portal Web, Owner Backoffice Web). Voir `docs/architecture.md`. Budget indicatif initial (250-300k FCFA, `concept.md` §6) correspondait à une v0 minimale ; le périmètre production-grade ci-dessous (multi-tenant, offline, observabilité, 3 apps) dépasse ce budget et doit être re-chiffré avec le client avant engagement.

## Phase 0 — Fondations techniques
- [x] Repo backend FastAPI, structure multi-tenant (Alembic, RLS PostgreSQL)
- [ ] Modèle de branches `feature/* → integration → main` (voir `docs/workflow.md`), protection des branches `integration`/`main` (pas de commit direct, PR obligatoire)
- [~] CI/CD de base (lint, tests, build Docker) pour le backend — workflow `.github/workflows/backend.yml` fait, déploiement auto vers staging sur `integration` et vers production sur `main`
- [x] 3 projets Flutter initialisés (Customer, Admin Portal, Owner Backoffice) avec thème/design system partagé
- [x] `codemagic.yaml` par app Flutter : workflows `integration` (distribution interne Firebase/TestFlight) et `main` (soumission Google Play + App Store) — voir `docs/workflow.md` §5
- [~] Environnements dev/staging/production séparés (côté code fait : config validée fail-closed hors dev, `.env.example` ; reste : provisionnement Vault/Secrets Manager et coffre Codemagic), gestion des secrets (Vault/Secrets Manager + coffre Codemagic pour keystore/certificats)

## Phase 1 — Design & UX
- [ ] Maquettes des parcours citoyen, admin émettrice/requérante, owner
- [ ] Flux offline explicités dans les maquettes (statuts "en attente de connexion", "vérifié hors-ligne")
- [ ] Choix du premier document type couvert (ex: certificat de résidence)

Pour les phases 2 à 4, chaque tâche suit `docs/workflow.md` §1 : implémentation + smoke tests ciblés avant de passer à la tâche suivante ; pas d'exécution e2e avant la Phase 5 (un backlog de scénarios e2e à couvrir peut être tenu au fil de l'eau, sans les exécuter).

## Phase 2 — Demande, pièce justificative, signature, QR + vérification offline
- [x] Endpoint de demande (`POST /requests`) avec `reference_document_id`, statut initial `pending_reference_check` — smoke test : création + statut
- [x] Contrôle d'existence du document référencé avant paiement (`notifications.md` §3) : `reference_not_found` vs `pending_payment` — smoke test : les deux issues, notification envoyée dans chaque cas
- [ ] Upload de pièce justificative via URL S3 pré-signée (`/requests/{id}/evidence/upload-url` + `/complete`), validation type/taille/hash — smoke test : upload valide accepté + notifié, type/taille invalide rejeté + notifié
- [ ] File de revue agent émettrice (`GET /issuer/requests?status=in_review`, `POST .../evidence/{id}/review`) — smoke test : accept/reject change bien le statut de la demande et déclenche la notification correspondante
- [ ] Service Notification : `NotificationEvent`, idempotence par `(document_request_id, event_type)`, envoi email/SMS/push pour chaque transition du tableau `notifications.md` §2 — smoke test : pas de double-envoi sur rejeu
- [ ] `DocumentRequestStatusHistory` + endpoint `GET /requests/{id}` avec timeline — smoke test : historique complet et dans l'ordre
- [ ] Job de relance sur délai dépassé (`estimated_ready_at`) — smoke test : notification + alerte agent déclenchées après dépassement simulé
- [ ] Endpoints réclamation (`POST /reclamations`, `GET /reclamations`, `POST /issuer/reclamations/{id}/respond`, `GET /owner/reclamations`) — smoke test : cycle open → resolved avec notification de réponse
- [ ] Génération de paire de clés PKI/ECC par tenant (HSM/KMS) — smoke test : clé générée, jamais exportable en clair
- [ ] Endpoint d'émission/signature (`POST /issuer/documents`) générant le **PDF final** avec QR code intégré, stockage PDF sur S3 — smoke test : PDF produit, signature valide sur le hash
- [ ] Endpoint `GET /documents/{id}/download` (URL signée, courte durée) — smoke test : URL expire après délai
- [ ] Endpoint `GET /verify/{qr_code_token}` — smoke test : document valide/invalide/expiré
- [ ] Endpoint `GET /verify/offline-bundle` (clés publiques + CRL signées) — smoke test : bundle signé, expiration correcte
- [ ] Endpoint `POST /verify/offline-log-sync` — smoke test : idempotence sur rejeu du même `local_id`
- [ ] Journalisation append-only (émission + vérification, avec champ `mode`) — smoke test : entrée non modifiable/supprimable

## Phase 3 — Intégration Mobile Money
- [ ] Adapters Orange Money / MTN MoMo / Moov Money (Celery, retries + idempotency keys) — smoke test par adapter : succès/échec/retry
- [ ] Webhooks de confirmation/échec (vérification de signature) — smoke test : webhook non signé rejeté, rejeu idempotent

## Phase 4 — Apps Flutter
- [ ] Customer App : demande (texte + référence document existant), capture/import photo de pièce justificative, paiement, portefeuille numérique PDF — smoke tests widget par écran
- [ ] Customer App : écran "mes démarches" (liste + timeline par demande), écran réclamation (créer/lister/rouvrir) — smoke tests widget
- [ ] Customer App : transmission (`share`) d'un document PDF vers une administration requérante, gestion/révocation des partages en cours — smoke test : partage créé/révoqué
- [ ] Customer App : mode offline (cache chiffré local, `OfflineOutbox` pour le formulaire texte uniquement — pas la photo, sync au retour réseau) — smoke test : sync idempotente
- [ ] Admin Portal (émettrice) : file de demandes en revue avec aperçu pièce justificative, accepter/rejeter, puis émission PDF — smoke tests widget
- [ ] Admin Portal (requérante) : réception des partages, vérification, historique (multi-tenant) — smoke tests widget
- [ ] Admin Portal : mode vérification offline (bundle clés/CRL) — smoke test : vérification sans réseau
- [ ] Owner Backoffice : gestion des tenants, abonnements, supervision d'usage, SSO+MFA — smoke tests widget
- [ ] Builds `integration` passant par Codemagic (distribution interne Firebase App Distribution / TestFlight) validés pour les 3 apps

## Phase 5 — Tests e2e, observabilité & déploiement
- [ ] **Exécution des tests end-to-end** des 3 parcours complets (incluant scénarios offline/sync) — première exécution de la suite e2e du projet, contre l'environnement staging (`integration`)
- [ ] Observabilité : OpenTelemetry, dashboards Grafana, alerting
- [ ] Démo avec 1 à 2 administrations pilotes (sur staging)
- [ ] Promotion `integration → main` (revue + e2e au vert, voir `docs/workflow.md` §2)
- [ ] Déploiement backend production depuis `main`
- [ ] Soumission Codemagic des 3 apps depuis `main` : Android → Google Play (piste interne/beta), iOS → App Store Connect/TestFlight ; promotion finale en production/store = validation humaine

## Post-MVP
- API de vérification en masse pour entreprises
- Option blockchain pour l'ancrage de preuve
- Impression certifiée via réseau de partenaires
- Extension à d'autres administrations/ministères (voir `concept.md` §8)
- Audit de sécurité externe + validation juridique de conformité
