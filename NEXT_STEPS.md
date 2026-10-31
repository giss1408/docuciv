# Prochaines étapes — DocuCiv

État actuel détaillé dans [`README.md`](./README.md). Ce document liste ce qui reste, dans l'ordre où `docs/roadmap.md` et `AGENTS.md` imposent de l'aborder.

## Pour clore la Phase 0 (Fondations techniques)

- [ ] **Protection de branches** sur l'hébergeur Git : interdire les commits directs sur `integration`/`main`, PR obligatoire (configuration plateforme, pas du code — nécessite un accès admin au repo).
- [ ] **Environnements réellement séparés** : dev/staging/production avec secrets distincts (Vault/Secrets Manager + coffre Codemagic pour keystore/certificats), au lieu des placeholders actuels (`.env.example`, mots de passe de migration `replace-at-deploy-time`).
- [ ] **OIDC réel** : `app/core/auth.py` n'implémente que la forme (vérification JWT, RBAC) — l'émission de token par un IdP (Keycloak ou équivalent) n'est pas branchée.
- [ ] Rendre `pip-audit`/Trivy effectivement bloquants en CI sur un vrai dépôt GitHub (actuellement validé en local uniquement, jamais exécuté sur un run CI réel faute d'accès).

## Phase 1 — Design & UX (bloquant avant tout écran métier)

- [ ] Maquettes des parcours citoyen, admin émettrice/requérante, owner.
- [ ] Flux offline explicités dans les maquettes ("en attente de connexion", "vérifié hors-ligne").
- [ ] Choix du premier document type couvert (ex: certificat de résidence).

**Règle AGENTS.md/roadmap** : pas d'écran métier réel avant ces maquettes — les 3 écrans placeholder actuels (`HomeScreen`, `RequestQueueScreen`, `TenantsScreen`) ne doivent pas être étoffés en UX inventée.

## Phase 2 — Demande, pièce justificative, signature, QR + vérification offline

Voir `docs/roadmap.md` pour le détail complet. Premiers blocs dans l'ordre :
1. `POST /requests` + contrôle d'existence du `reference_document_id` avant paiement (`docs/notifications.md` §3)
2. Upload `SourceEvidence` via URL S3 pré-signée, validation type/taille/hash
3. File de revue agent émettrice + `NotificationEvent` idempotent
4. `DocumentRequestStatusHistory` + `GET /requests/{id}` (timeline)
5. Génération de clé PKI/ECC par tenant (HSM/KMS) + endpoint de signature produisant le PDF final
6. `GET /verify/{qr_code_token}`, `GET /verify/offline-bundle`, `POST /verify/offline-log-sync`

Chaque bloc suit `docs/workflow.md` §1 : implémentation + smoke tests ciblés, pas d'e2e avant la fin de la Phase 2. Chaque endpoint touchant une table tenantée doit avoir un test BOLA avant merge, sur le modèle de `backend/tests/test_rls_isolation.py`.

## Phase 3 — Intégration Mobile Money

- [ ] Adapters Orange Money / MTN MoMo / Moov Money (idempotency keys, retries)
- [ ] Webhooks de confirmation avec vérification de signature

## Phase 4 — Apps Flutter (écrans métier réels)

Ne démarre qu'après les maquettes de Phase 1 et les endpoints correspondants de Phase 2/3. Les 3 apps consommeront `docuciv_design_system` (tokens, thème clair/sombre, composants partagés) déjà en place.

## Phase 5 — e2e, observabilité, déploiement

- [ ] Première exécution de la suite e2e complète contre `integration`
- [ ] OpenTelemetry + dashboards Grafana + alerting
- [ ] Démo pilote, promotion `integration → main`, déploiement production, soumission stores via Codemagic

## Dette / points ouverts transverses

- Hébergement (AWS Cape Town vs. datacenter Abidjan) — décision ouverte, voir `docs/architecture.md` §7.
- Validation juridique de la signature électronique ivoirienne et DPIA RGPD/CNIL-CI avant tout pilote avec données d'état civil réelles (`docs/security.md` §13/§15).
- Pentest externe avant toute mise en production avec un partenaire gouvernemental (`docs/security.md` §14).
