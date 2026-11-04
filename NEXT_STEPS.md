# NEXT_STEPS — DocuCiv

État au 2 novembre 2026. Source de vérité des tâches : [`docs/roadmap.md`](./docs/roadmap.md). Règles de travail : [`AGENTS.md`](./AGENTS.md).

## 1. Où en est le dépôt

| Branche | Contenu | Dans `integration` ? |
|---|---|---|
| `feature/phase0-*` (4 branches) | Backend FastAPI + RLS, 3 apps Flutter + thème partagé, `codemagic.yaml`, config par environnement | Oui |
| `feature/phase2-requests` | `POST /requests`, historique de statuts en ajout seul | Oui |
| `feature/phase2-reference-check` | Contrôle d'existence avant paiement, machine à états, événements de notification idempotents | Oui |
| `feature/phase2-evidence-upload` | Upload de pièce par POST S3 pré-signé, MIME réel, EXIF, antivirus | **Non** |
| `feature/phase2-issuer-review` | File de revue agent, consultation de pièce, accepter/rejeter, `in_review` automatique | **Non** (contient la branche précédente) |
| `feature/phase2-get-requests` | `GET /requests` et `GET /requests/{id}` avec timeline | **Non** (contient les deux précédentes) |

Tests : 68 passent, 2 ignorés (`tests/test_s3_storage.py`, voir §3). Aucun test e2e n'a été écrit ni lancé, conformément à `docs/workflow.md` §1.

## 2. À faire tout de suite (humain)

1. **Merger `feature/phase2-get-requests` dans `integration`.** Elle contient `phase2-evidence-upload` et `phase2-issuer-review`, un seul merge suffit.
2. **Authentifier `gh`** (`gh auth login`) pour repasser par des PR. Les merges Phase 0 et Phase 2 ont été faits en local puis poussés directement sur `integration`, ce que la règle 15 de `AGENTS.md` interdit en temps normal.
3. **Protéger `integration` et `main` sur GitHub** : PR obligatoire, CI verte requise, pas de push direct.
4. **Vérifier que la CI GitHub est verte.** `.github/workflows/backend.yml` n'a jamais été vu en exécution.
5. **Créer le projet Codemagic** et ses groupes de variables : `customer_android_signing`, `customer_firebase`, `google_play_production`, `app_store_connect`. `codemagic.yaml` n'a jamais tourné.
6. **Lancer le test S3 réel** sur une machine qui accède à quay.io :
   `docker compose up -d minio postgres && DOCUCIV_TEST_S3=1 DOCUCIV_TEST_DB=1 pytest`.

## 3. Ce qui n'est pas vérifié

- **POST S3 pré-signé** : la taille max et le Content-Type exact sont censés être appliqués par S3. Les tests utilisent un faux stockage. Test écrit, jamais exécuté (MinIO impossible à tirer depuis cet environnement).
- **SSE-KMS** : codé, jamais testé.
- **ClamAV** : le protocole INSTREAM est testé contre un faux `clamd`, jamais contre un vrai.
- **Flutter** : version 3.24.2 (septembre 2024). À mettre à jour avant de figer la version dans Codemagic.

## 4. Décisions à prendre

| Sujet | Pourquoi ça bloque |
|---|---|
| **Fournisseur SMS** (Orange CI, Twilio, autre) | Transport SMS du service Notification |
| **Fournisseur email** (SES, Postmark, autre) | Transport email du service Notification |
| **Push** (FCM/APNs via Firebase) | Transport push |
| **Tarification** : montant par tenant et type de document | `amount_due` vaut 1000 FCFA en dur dans la config (`default_amount_due_fcfa`) |
| **Politique de remboursement** par tenant | Le rejet en revue ne rembourse rien aujourd'hui (le paiement n'existe pas) |
| **Liste complète des types de document** | Seuls 4 types sont supportés (`acte_naissance`, `certificat_residence`, `car`, `permis_conduire`) |
| **HSM/KMS** : AWS KMS, GCP KMS ou HSM à Abidjan | Bloque la génération de clés et la signature, donc l'émission |
| **Hébergement** : AWS Cape Town ou Abidjan | `docs/architecture.md` §7 |
| **IdP OIDC** : Keycloak ou autre | Remplace les en-têtes `X-Dev-*` ; hors dev, tout est en 401 d'ici là |
| **Jours fériés ivoiriens** pour le calcul de `estimated_ready_at` | Le calcul ignore seulement les week-ends |

## 5. Prochaines tâches de code (Phase 2, dans l'ordre proposé)

1. **Service Notification complet** : worker Celery + Redis, transports email/SMS/push, passage de `pending` à `sent`/`failed`. Les événements sont déjà enregistrés de façon idempotente. Dépend des fournisseurs du §4.
2. ~~**Job de relance**~~ **Code fait** sur `feature/phase2-relance-job` (non commitée, non mergée) : `app/services/followup.py`, migration 0006, filtre `GET /issuer/requests?overdue=true`. Reste à le brancher sur Celery beat (`python -m app.services.followup` en attendant) ; ses tests DB (`tests/test_followup.py`) passent (73 passed, 2 skipped S3). La fonction SECURITY DEFINER suppose que le rôle de migration contourne la RLS (vrai en dev, à vérifier en staging).
3. **Réclamations** : `POST /reclamations`, `GET /reclamations`, réponse côté émetteur, vue Owner.
4. **Clés PKI/ECC par tenant** (HSM/KMS) : jamais de clé privée exportable, une clé retirée n'est jamais supprimée.
5. **`POST /issuer/documents`** : PDF avec QR code, hash, signature, horodatage RFC 3161, stockage S3.
6. **`GET /documents/{id}/download`**, **`GET /verify/{qr_code_token}`**, **`GET /verify/offline-bundle`**, **`POST /verify/offline-log-sync`**.
7. **Journalisation append-only** émission et vérification, avec le champ `mode`.

Puis Phase 3 (Mobile Money : adapters Orange/MTN/Moov, webhooks signés). Le webhook de paiement doit appeler `enter_review_if_ready` (`backend/app/services/review.py`) après le passage à `paid`.

## 6. Dettes techniques connues

- Le contrôle d'existence tourne en `BackgroundTasks` FastAPI, pas en Celery. Si le processus s'arrête, la demande reste en `pending_reference_check` jusqu'au job de relance.
- Un `reference_check` de type `unverifiable` n'est pas encore signalé visuellement à l'agent, seulement exposé dans la liste.
- La revue d'une pièce règle la demande entière ; les autres pièces en attente ne sont pas revues.
- Les PDF de pièces justificatives gardent leurs métadonnées (seul le contenu actif est refusé).
- Pas d'endpoint pour gérer `processing_delay_configs` ; la table est remplie à la main.
- Pas de rate limiting sur `/requests` ni sur l'upload (`docs/security.md` §2).
- Pas de préfixe `/api/v1` (`docs/security.md` §2 le demande).
- Phase 1 (maquettes, parcours offline, choix du premier type de document) non réalisée : elle ne produit pas de code.
- Phase 4 (écrans Flutter) non commencée : les 3 apps affichent seulement une coquille avec le thème.
