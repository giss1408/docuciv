# Architecture technique — DocuCiv (production grade)

## 1. Stack retenue

| Couche | Technologie |
|---|---|
| Backend API | Python 3.12, **FastAPI** (async), Pydantic v2 |
| Workers / tâches async | **Celery** + Redis (ou RabbitMQ) pour signature, envoi email/SMS, génération PDF/QR, webhooks sortants |
| Base de données | **PostgreSQL 16** (primaire), **Redis** (cache, rate limiting, idempotence) |
| Migrations | Alembic |
| Stockage fichiers | S3-compatible (AWS S3 / MinIO on-prem Abidjan) — documents PDF signés, jamais en base |
| Signature cryptographique | `cryptography` (ECC P-256) + HSM/KMS pour la clé privée des émetteurs ; horodatage RFC 3161 |
| Auth | OAuth2/OIDC (citoyens via Keycloak ou Auth0-like ; administrations via client_credentials + mTLS optionnel) |
| Apps mobiles/web client | **Flutter** (iOS, Android, Web) — un seul codebase par app, 3 apps distinctes (voir §2) |
| Observabilité | OpenTelemetry (traces/metrics) → Prometheus + Grafana, logs structurés JSON → Loki/ELK |
| CI/CD backend | GitHub Actions (ou GitLab CI) : lint, tests, build Docker, déploiement |
| CI/CD apps Flutter | **Codemagic** : build Android (Google Play) et iOS (App Store), distribution interne sur `integration`, soumission store sur `main` — voir `docs/workflow.md` |
| Infra | Docker + Kubernetes (ou ECS) ; Terraform pour l'infra as code ; hébergement AWS Cape Town ou datacenter Abidjan selon souveraineté des données |
| Secrets | Vault / AWS Secrets Manager — jamais en clair dans le repo ou les variables CI en dur |

## 2. Applications (3 apps Flutter distinctes)

### Customer App — iOS, Android, Web
- Public : citoyens et entreprises.
- Fonctions : demande de document, paiement Mobile Money, portefeuille numérique, partage contrôlé.
- Build Flutter unique, 3 cibles (`flutter build ios`, `apk/appbundle`, `web`).

### Admin Portal — Web (Flutter Web)
- Public : agents des administrations émettrices et requérantes (rôle par tenant).
- Fonctions : file de demandes, émission/signature, vérification, historique, gestion des agents du tenant.
- Pas de version mobile native au MVP (usage bureau) ; Flutter Web responsive.

### Owner Backoffice — Web (Flutter Web)
- Public : équipe DocuCiv (opérateur de la plateforme SaaS).
- Fonctions : gestion des tenants (administrations), facturation/abonnements, supervision globale, support, feature flags, monitoring applicatif de haut niveau.
- Accès restreint : SSO interne + MFA obligatoire.

Les 3 apps consomment la **même API backend** via des scopes/rôles différents — pas d'API dupliquée.

### Mode offline (Customer App + Admin Portal)

- **Customer App (mobile)** : stockage local chiffré (`sqlite` via `drift`/`sqflite` + `flutter_secure_storage` pour les clés) du portefeuille de documents déjà téléchargés (PDF + métadonnées), consultables et partageables sans réseau. Les demandes créées hors-ligne sont mises en file (`outbox` locale) et synchronisées dès reconnexion (sync bidirectionnelle avec résolution de conflits côté serveur, le serveur étant toujours source de vérité pour le statut et la signature).
- **Admin Portal (terrain, ex. vérification en zone peu connectée)** : mode vérification offline limité — cache local des clés publiques des émetteurs + liste de révocation (CRL) téléchargée périodiquement, permettant de vérifier une signature ECC et un hash **sans** appel réseau. Le résultat est marqué `verified_offline` et resynchronisé (log d'audit) dès reconnexion ; ne jamais permettre l'émission de document en mode offline (nécessite toujours le service de signature en ligne, clé privée jamais sur l'appareil).
- **Owner Backoffice** : pas de mode offline (usage interne, toujours connecté).
- **Principe général** : offline = lecture/consultation/vérification dégradée, jamais écriture critique (paiement, émission) sans confirmation serveur. Toute action en attente de sync est visible à l'utilisateur avec un statut explicite ("en attente de connexion").

## 3. Vue d'ensemble des services backend

```
                 ┌───────────────────────────────┐
                 │        API GATEWAY (FastAPI)   │
                 │  authn (OIDC/API key) + authz  │
                 │  rate limiting, tenant routing  │
                 └───────────────┬─────────────────┘
        ┌────────────────────────┼────────────────────────┐
┌───────▼───────┐       ┌────────▼────────┐       ┌────────▼────────┐
│ Requests &     │       │ Signature        │       │ Verification &  │
│ Documents svc  │       │ service (Celery) │       │ Traceability svc │
│ (CRUD, state   │       │ ECC/PKI, HSM,    │       │ QR decode, hash  │
│ machine)       │       │ timestamp (RFC   │       │ check, audit log │
│                │       │ 3161)             │       │ (append-only)    │
└───────┬────────┘       └────────┬─────────┘       └────────┬─────────┘
        │                          │                           │
┌───────▼────────┐       ┌────────▼─────────┐       ┌─────────▼────────┐
│ Payment svc     │       │ Notification svc  │       │ Tenant & Billing  │
│ (Orange/MTN/    │       │ (email/SMS/push,  │       │ svc (Owner        │
│ Moov adapters)  │       │  Celery, idempot.) │       │ Backoffice data)  │
└─────────────────┘       └─────────┬─────────┘       └────────────────────┘
                                     │
                           ┌─────────▼─────────┐
                           │ Reclamation svc    │
                           │ (file par tenant / │
                           │  Owner, SLA, audit)│
                           └───────────────────┘
                 ┌───────────────────────────────┐
                 │  PostgreSQL (multi-tenant,     │
                 │  row-level isolation) + Redis  │
                 │  + S3 (documents PDF)          │
                 └───────────────────────────────┘
```

Le **Notification service** émet un message à chaque transition d'état de `DocumentRequest` (succès ou échec) — jamais seulement au succès final. Le détail complet des messages, canaux et déclencheurs est spécifié dans `docs/notifications.md`, référence obligatoire pour toute implémentation touchant au cycle de vie d'une demande.

## 4. Multi-tenancy

- Chaque **Administration** (émettrice ou requérante) est un **tenant**.
- Isolation logique via `tenant_id` sur toutes les tables métier + Row-Level Security PostgreSQL (policy au niveau DB, pas un simple filtre applicatif — voir `security.md` §2/§4 et `data-model.md` §4).
- Chaque endpoint touchant une entité tenantée doit avoir un test automatisé d'accès croisé entre deux tenants factices, exécuté en CI, bloquant avant merge (défense BOLA).
- Le **Owner Backoffice** opère au-dessus de tous les tenants (super-admin), jamais exposé aux autres apps ; tout accès transverse est journalisé dans `PlatformAuditLog` avec justification obligatoire, et les actions à fort impact (suspension de tenant, révocation de clé racine) passent par un `OwnerApprovalRequest` à double contrôle (voir `data-model.md`).
- Scaling horizontal : stateless API (FastAPI), sessions dans Redis, workers Celery scalables indépendamment des APIs.

## 4bis. Gestion des clés de signature (hiérarchie)

- **Clé racine plateforme** (`SigningKey.key_type = platform_root`) : signe le `offline-bundle` (clés publiques + CRL) et atteste les clés publiques des tenants. Génération en cérémonie documentée, opérations soumises à quorum/double contrôle, jamais exportable du HSM.
- **Clé par tenant** (`SigningKey.key_type = tenant`) : signe les documents émis par ce tenant. Rotation planifiée (ex. annuelle) et rotation d'urgence en cas de compromission — procédure détaillée dans `security.md` §3.
- Une clé retirée ou compromise n'est jamais supprimée (historisée avec `status = retired/compromised`) pour que les documents déjà émis restent vérifiables.
- Une compromission de clé déclenche : révocation immédiate propagée au `offline-bundle` (`RevocationEntry`), marquage `under_review` des documents émis après la date de compromission estimée, notification des tenants concernés, ré-émission.

## 5. Flux principal (demande → vérification d'existence → paiement → émission → transmission → vérification)

Chaque étape notifie le citoyen (succès **et** échec) — voir `docs/notifications.md` §2 pour le message exact de chaque transition ; non répété ici en détail.

1. **Customer App** : citoyen crée une `DocumentRequest` en renseignant le `reference_document_id` (numéro du document existant, ex. ancien acte à renouveler). Statut initial `pending_reference_check`.
2. **Contrôle d'existence** (avant tout paiement, voir `notifications.md` §3) : vérification du `reference_document_id` auprès de l'administration émettrice (API si disponible, sinon file de vérification manuelle rapide). Résultat `reference_not_found` (échec terminal, notifié, pas de paiement demandé) ou `pending_payment` (notifié, le citoyen peut continuer).
3. Citoyen **téléverse une photo/scan** du document (`SourceEvidence`) — upload direct vers S3 via URL pré-signée (le fichier ne transite jamais par l'API applicative en clair), `mime_type` et taille validés côté serveur, hash SHA-256 calculé à l'upload. Upload invalide (type/taille rejeté, antivirus) → notifié immédiatement, citoyen invité à recommencer.
4. Citoyen initie le paiement Mobile Money (adapter dédié par opérateur, idempotent via clé Redis) → webhook de confirmation (signature vérifiée) fait transitionner la demande vers `paid` (notifié) ou `pending_payment` avec échec signalé si le webhook indique un échec (notifié, citoyen invité à réessayer).
5. **Admin Portal (émettrice)** : la demande passe en `in_review` ; un agent examine la `SourceEvidence` (photo lisible ? cohérente avec le `reference_document_id` et le type de document demandé ?) et l'accepte (`review_status = accepted` → `DocumentRequest.status = in_progress`, notifié avec délai estimé) ou la rejette (`rejected`, avec `rejection_reason`, notifié, remboursement/traitement du paiement selon la politique métier).
6. **Service Signature** (worker Celery) : génère le **document final au format PDF**, insère le QR code de sécurité, calcule le hash SHA-256 du PDF final, signe avec la `SigningKey` active du tenant (ECC via HSM/KMS, voir §4bis), horodate (RFC 3161), stocke le PDF signé sur S3 (`pdf_storage_key`). `DocumentRequest.status = issued` (notifié).
7. **Notification service** : envoie au citoyen le PDF signé (lien de téléchargement sécurisé, pas le fichier en pièce jointe brute) par email/SMS/push ; document ajouté au portefeuille numérique (Customer App), téléchargeable pour consultation offline.
8. **Transmission à une administration requérante** : le citoyen crée un `DocumentShare` (lien à usage/durée limités, ou transfert in-app si l'administration requérante est aussi utilisatrice de l'Admin Portal) pour transmettre le PDF — jamais le fichier brut par un canal non tracé (pas d'email libre hors plateforme pour le flux officiel).
9. **Admin Portal (côté requérante)** : ouverture du lien de partage, ou scan du QR code imprimé/affiché depuis le PDF, ou saisie manuelle du numéro → service Vérification confirme authenticité/intégrité/émetteur/dates à partir du PDF reçu (recalcul du hash et vérification de la signature), journalise l'événement (append-only, `VerificationLog`).

**À tout moment** : le citoyen peut consulter le statut courant de sa demande (`GET /requests/{id}`, timeline complète) sans attendre une notification, et déposer une réclamation (`POST /reclamations`) s'il perçoit une anomalie — voir `notifications.md` §5-6. Un job planifié détecte les demandes dont le délai estimé est dépassé et relance automatiquement (citoyen notifié + agent émetteur alerté).

## 6. Exigences de production

- **Haute disponibilité** : API en plusieurs réplicas derrière un load balancer, PostgreSQL avec réplication (primaire + réplicas lecture), Redis en mode sentinel/cluster.
- **Observabilité** : dashboards Grafana (latence API, taux d'échec paiement, volume signatures/jour), alerting (PagerDuty/Opsgenie) sur échecs de signature ou webhooks paiement.
- **Résilience paiement** : retries avec backoff exponentiel sur les appels Mobile Money, idempotency keys sur chaque tentative.
- **Sauvegardes** : backups PostgreSQL chiffrés automatisés, test de restauration périodique ; S3 versionné.
- **CI/CD** : pipeline par app (backend Python, 3 apps Flutter) avec tests automatisés obligatoires avant déploiement — y compris tests d'isolation tenant (BOLA, voir §4) et scan de dépendances/SCA bloquant sur vulnérabilités critiques/high (voir `security.md` §10) ; déploiements progressifs (canary/blue-green) pour le backend. Ordre de test (smoke tests pendant l'implémentation, e2e seulement en fin de phase ou sur `integration`) et modèle de branches (`feature/* → integration → main`) détaillés dans `docs/workflow.md`.
- **Environnements** : dev / staging (`integration`) / production (`main`) strictement séparés, secrets distincts par environnement (Vault/Secrets Manager, jamais en clair dans les manifests).
- **Support offline** : API conçue idempotente (clé d'idempotence sur les créations) pour supporter les rejeux de sync après reconnexion ; endpoint dédié de distribution des clés publiques/CRL pour la vérification offline (`GET /verify/offline-bundle`, mis en cache côté client avec expiration courte).

## 7. Décisions ouvertes

- **Hébergement** : AWS Cape Town vs. datacenter Abidjan — dépend des exigences de souveraineté des partenaires gouvernementaux (voir `security.md`).
- **Blockchain** : non requis au MVP ; option d'ancrage de hash post-MVP si un partenaire l'exige pour la confiance publique.
