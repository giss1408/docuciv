# Modèle de données — DocuCiv

## 1. Entités principales

Toutes les tables métier (hors `OwnerUser`, `PlatformAuditLog`) portent un `tenant_id` (FK `Administration`) et sont protégées par Row-Level Security PostgreSQL. Le rôle **Owner** (plateforme DocuCiv) n'a pas de `tenant_id` et peut lire tous les tenants via un accès explicite de supervision.

### User
Représente un citoyen ou une entreprise.
| Champ | Type | Description |
|---|---|---|
| id | UUID | Identifiant |
| type | enum(`citizen`,`business`) | Type de demandeur |
| full_name / company_name | string | Nom |
| phone | string | Utilisé pour SMS et Mobile Money |
| email | string | Utilisé pour notifications |
| national_id | string (nullable) | Pièce d'identité, si applicable |
| created_at | timestamp | |

### Administration (tenant)
Représente une entité émettrice ou requérante (peut être les deux). Unité d'isolation multi-tenant. Ne porte plus la clé de signature directement (voir `SigningKey`) — un tenant peut avoir plusieurs clés au fil des rotations.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| name | string | Ex: "Mairie d'Abidjan", "DGI" |
| role | enum(`issuer`,`verifier`,`both`) | Rôle dans la plateforme |
| api_key_hash | string (secret) | Hash de la clé d'intégration API (jamais stockée en clair) |
| subscription_tier | string | Lié à la tarification (voir concept.md §4) |
| status | enum(`active`,`suspended`) | Géré par le Owner Backoffice, changement soumis à double contrôle (voir `OwnerApprovalRequest`) |
| created_at | timestamp | |

### SigningKey
Clé de signature d'un tenant, gérée dans le HSM/KMS (seule la référence/clé publique est stockée ici — la clé privée ne quitte jamais le HSM). Historisée : une clé retirée n'est jamais supprimée, seulement marquée `retired`/`compromised`, pour que les documents déjà émis restent vérifiables (voir `security.md` §3).
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| tenant_id | UUID (FK Administration, nullable pour la clé racine plateforme) | |
| key_type | enum(`tenant`,`platform_root`) | La clé racine plateforme signe le `offline-bundle` et atteste les clés publiques tenants |
| public_key | string | |
| hsm_key_ref | string | Référence opaque vers la clé privée dans le HSM/KMS, jamais la clé elle-même |
| status | enum(`active`,`retired`,`compromised`) | `compromised` propage immédiatement une entrée dans `RevocationEntry` |
| activated_at | timestamp | |
| retired_at | timestamp (nullable) | |
| rotation_reason | enum(`scheduled`,`compromise`) (nullable) | |

### RevocationEntry
Alimente la CRL distribuée via `GET /verify/offline-bundle`. Peut révoquer une `SigningKey` (compromission) ou un `Document` précis.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| target_type | enum(`signing_key`,`document`) | |
| target_id | UUID | FK vers `SigningKey.id` ou `Document.id` selon `target_type` |
| reason | string | |
| revoked_at | timestamp | |

### OwnerApprovalRequest
Support du double contrôle (four-eyes) sur les actions Owner à fort impact (suspension de tenant, révocation de clé racine, export massif de données — voir `security.md` §6). Une action n'est exécutée qu'après une deuxième approbation d'un `OwnerUser` distinct de l'initiateur.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| action | string | Ex: `suspend_tenant`, `revoke_root_key` |
| target_tenant_id | UUID (nullable) | |
| requested_by | UUID (FK OwnerUser) | |
| justification | string | Obligatoire |
| approved_by | UUID (FK OwnerUser, nullable) | Doit différer de `requested_by` |
| status | enum(`pending`,`approved`,`rejected`,`executed`) | |
| created_at / decided_at | timestamp | |

### AdminAgent
Compte d'un agent d'une administration (utilisateur de l'Admin Portal), scoped à un seul `tenant_id`.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| tenant_id | UUID (FK Administration) | |
| full_name | string | |
| email | string | |
| role | enum(`issuer_agent`,`verifier_agent`,`tenant_admin`) | |
| created_at | timestamp | |

### OwnerUser
Compte de l'équipe DocuCiv (Owner Backoffice). Pas de `tenant_id` — accès transverse.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| full_name | string | |
| email | string | |
| mfa_enabled | boolean | Obligatoire pour ce rôle |
| created_at | timestamp | |

### DocumentRequest
Demande initiée par un `User`. Le citoyen fournit en plus du formulaire une référence vers le document existant (ex. numéro d'acte à renouveler) et une pièce justificative photographiée — voir `SourceEvidence`.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| user_id | UUID (FK User) | |
| administration_id | UUID (FK Administration) | Émetteur visé |
| document_type | enum | acte_naissance, certificat_residence, car, permis_conduire, ... |
| reference_document_id | string | Numéro/ID du document existant fourni par le citoyen (ex. n° d'acte de naissance à dupliquer/renouveler) |
| status | enum(`pending_reference_check`,`reference_not_found`,`pending_payment`,`paid`,`in_review`,`in_progress`,`issued`,`rejected`) | Voir `notifications.md` §2/§3 pour le détail de chaque transition et son message associé |
| rejection_reason | string (nullable) | Renseigné si `status = rejected` (ex. pièce illisible, incohérente, dossier incomplet côté administration) |
| estimated_ready_at | timestamp (nullable) | Calculé à l'entrée en `in_progress` à partir de la configuration de délai par tenant/type de document (voir `notifications.md` §4) |
| payload | jsonb | Données du formulaire |
| created_at / updated_at | timestamp | |

### DocumentRequestStatusHistory
Historique append-only de chaque transition de statut d'une `DocumentRequest`, utilisé pour la timeline affichée au citoyen (`GET /requests/{id}`, voir `notifications.md` §5) et pour le support.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_request_id | UUID (FK) | |
| from_status | enum (nullable) | |
| to_status | enum | |
| reason | string (nullable) | |
| changed_at | timestamp | |

### NotificationEvent
Trace chaque notification envoyée à un `User` (ou `AdminAgent`/`OwnerUser` pour les relances internes). Ne stocke jamais le contenu complet d'un message contenant des PII (voir `notifications.md` §7).
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_request_id | UUID (FK, nullable) | |
| user_id | UUID (FK User, nullable) | |
| event_type | enum | Correspond aux lignes du tableau `notifications.md` §2 (ex. `evidence_rejected`, `payment_confirmed`, `document_issued`, `delay_exceeded`, ...) |
| channel | enum(`email`,`sms`,`push`,`in_app`) | |
| send_status | enum(`sent`,`failed`,`skipped_duplicate`) | `skipped_duplicate` = bloqué par la clé d'idempotence `(document_request_id, event_type)` |
| idempotency_key | string | `{document_request_id}:{event_type}` |
| created_at | timestamp | |

### Reclamation
Signalement d'un citoyen, lié à une `DocumentRequest` quand c'est possible. Voir `notifications.md` §6.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| user_id | UUID (FK User) | |
| document_request_id | UUID (FK, nullable) | Absent si la réclamation ne concerne pas une demande précise |
| category | enum(`delay`,`document_error`,`payment_issue`,`evidence_rejected_wrongly`,`fraud_suspicion`,`other`) | |
| description | string | |
| status | enum(`open`,`in_progress`,`resolved`,`rejected`,`reopened`) | |
| sla_response_due_at | timestamp | Calculé à la création selon `category` (SLA plus court pour `payment_issue`/`fraud_suspicion`, voir `notifications.md` §6) |
| handled_by | UUID (FK AdminAgent ou OwnerUser, nullable) | Admin Portal si liée à un tenant, Owner Backoffice si transverse/plateforme |
| response | string (nullable) | |
| created_at / updated_at | timestamp | |

### SourceEvidence
Pièce justificative fournie par le citoyen à l'appui d'une `DocumentRequest` (photo du document existant, ex. ancien acte, pièce d'identité). Stockée sur S3, jamais en base, chiffrée au repos (voir `security.md` §7).
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_request_id | UUID (FK) | |
| file_storage_key | string | Clé S3 de l'image/scan (jpg/png/pdf) |
| content_hash | string | SHA-256 du fichier au moment de l'upload, pour détecter toute substitution ultérieure |
| mime_type | string | Validé côté serveur (pas de confiance sur l'extension client) |
| uploaded_at | timestamp | |
| reviewed_by | UUID (FK AdminAgent, nullable) | Agent émetteur ayant examiné la pièce |
| review_status | enum(`pending`,`accepted`,`rejected`) | |
| review_notes | string (nullable) | |

### Transaction
Paiement Mobile Money lié à une `DocumentRequest`.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_request_id | UUID (FK) | |
| provider | enum(`orange_money`,`mtn_momo`,`moov_money`) | |
| amount | integer | Montant en FCFA |
| status | enum(`initiated`,`confirmed`,`failed`) | |
| provider_reference | string | Référence externe du fournisseur |
| created_at | timestamp | |

### Document
Document final émis et signé, toujours produit au format **PDF** (format unique de livraison au citoyen et de transmission à une administration requérante — le PDF intègre le QR code de sécurité en page de garde ou en pied de page).
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_request_id | UUID (FK) | |
| administration_id | UUID (FK, émetteur, = tenant_id) | |
| signing_key_id | UUID (FK SigningKey) | Clé exacte utilisée — permet de retrouver/invalider les documents d'une clé compromise |
| content_hash | string | Hash du PDF final (SHA-256), calculé après insertion du QR code |
| signature | string | Signature cryptographique (PKI/ECC) sur `content_hash` |
| issued_at | timestamp | Horodatage certifié |
| expires_at | timestamp (nullable) | |
| qr_code_token | string | Jeton encodé dans le QR code intégré au PDF |
| status | enum(`active`,`revoked`,`expired`) | |
| pdf_storage_key | string | Clé S3 du PDF signé final (jamais stocké en base) |
| format | const(`pdf`) | Verrouillé à `pdf` — pas d'autre format de sortie au MVP |

### DocumentShare
Transmission d'un `Document` par le citoyen vers une administration requérante (ou tout destinataire désigné), à usage et durée limités. Matérialise le "renvoyé/transmis" évoqué dans le parcours citoyen.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_id | UUID (FK Document) | |
| shared_by_user_id | UUID (FK User) | |
| recipient_administration_id | UUID (FK Administration, nullable si lien public) | |
| share_token | string | Jeton opaque haute entropie, distinct du `qr_code_token` du document |
| delivery_method | enum(`link`,`email`,`sms`,`in_app_transfer`) | |
| max_uses | integer | Ex: 1 pour usage unique |
| use_count | integer | |
| expires_at | timestamp | |
| revoked_at | timestamp (nullable) | Révocable par le citoyen à tout moment |
| created_at | timestamp | |

### VerificationLog
Trace de chaque vérification effectuée.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| document_id | UUID (FK) | |
| verifying_administration_id | UUID (FK, nullable si vérification publique) | |
| result | enum(`valid`,`invalid`,`expired`,`revoked`) | |
| verified_at | timestamp | |
| mode | enum(`online`,`offline`) | `offline` = vérifié localement via cache de clés publiques/CRL, resynchronisé après coup |
| synced_at | timestamp (nullable) | Renseigné uniquement si `mode = offline`, au moment de la resynchronisation |

### OfflineOutbox (local client uniquement, non répliqué en base serveur)
File d'attente locale (Customer App) pour les demandes créées hors-ligne, en `sqlite` chiffré sur l'appareil.
| Champ | Type | Description |
|---|---|---|
| local_id | UUID | Généré côté client, utilisé comme clé d'idempotence à la synchronisation |
| payload | jsonb | Contenu de la `DocumentRequest` en attente |
| created_at_local | timestamp | |
| sync_status | enum(`pending`,`synced`,`failed`) | |

### PlatformAuditLog
Journal append-only (non supprimable, y compris par un Owner — voir `security.md` §6) des actions du rôle Owner : création/suspension de tenant, changement de tarification, tout accès en lecture aux données d'un tenant (avec justification), opérations sur `SigningKey`/`RevocationEntry`. Pas de `tenant_id`.
| Champ | Type | Description |
|---|---|---|
| id | UUID | |
| owner_user_id | UUID (FK OwnerUser) | |
| action | string | |
| target_tenant_id | UUID (nullable) | |
| justification | string (nullable) | Obligatoire pour tout accès en lecture aux données d'un tenant |
| created_at | timestamp | |

## 2. Relations

- `User` 1—N `DocumentRequest`
- `Administration` (émetteur) 1—N `DocumentRequest`
- `Administration` 1—N `SigningKey` (historique des clés, y compris retirées/compromises)
- `Administration` 1—N `AdminAgent`
- `DocumentRequest` 1—1 `Transaction`
- `DocumentRequest` 1—N `SourceEvidence` (au moins 1 attendue : la photo/scan du document référencé)
- `DocumentRequest` 1—N `DocumentRequestStatusHistory` (une entrée par transition)
- `DocumentRequest` 1—N `NotificationEvent`
- `DocumentRequest` 0—N `Reclamation`
- `DocumentRequest` 1—1 `Document` (créé une fois le document émis)
- `Document` N—1 `SigningKey` (clé utilisée pour signer)
- `Document` 1—N `VerificationLog`
- `Document` 1—N `DocumentShare` (transmission à une ou plusieurs administrations requérantes)
- `SigningKey` 0—N `RevocationEntry` (si compromise)
- `Document` 0—N `RevocationEntry` (si révoqué individuellement)
- `OwnerUser` 1—N `OwnerApprovalRequest` (comme demandeur ou approbateur)
- `User` 1—N `Reclamation`

## 3. États clés

`DocumentRequest.status` :
`pending_reference_check → pending_payment → paid → in_review → in_progress → issued` (ou `reference_not_found` dès le premier contrôle si le document référencé n'existe pas — échec terminal, jamais de paiement demandé ; ou `rejected` à tout moment après `paid` avec `rejection_reason` renseigné — ex. pièce justificative illisible/invalidée, ou dossier incomplet découvert en `in_progress`). `pending_reference_check` = vérification de l'existence du `reference_document_id` auprès de l'administration émettrice avant tout paiement (voir `notifications.md` §3). `in_review` = la `SourceEvidence` est examinée par un agent avant que la production du document ne démarre. Chaque transition crée une `DocumentRequestStatusHistory` et déclenche la notification correspondante (`notifications.md` §2).

`SourceEvidence.review_status` :
`pending → accepted` (débloque le passage de `DocumentRequest` à `in_progress`) ou `pending → rejected` (fait passer `DocumentRequest` à `rejected`)

`Document.status` :
`active → expired` (automatique selon `expires_at`) ou `active → revoked` (action administrative, via `RevocationEntry`)

`DocumentShare` :
créé après `Document.status = active` ; usage borné par `max_uses`/`expires_at`, ou révocable manuellement (`revoked_at`) par le citoyen à tout moment — ne change jamais le statut du `Document` lui-même.

`SigningKey.status` :
`active → retired` (rotation planifiée) ou `active → compromised` (incident — déclenche la procédure de `security.md` §3 : révocation immédiate, marquage `under_review` des documents émis après la date de compromission estimée, ré-émission)

`OwnerApprovalRequest.status` :
`pending → approved → executed` ou `pending → rejected` (l'action cible n'est jamais exécutée avant `approved`, et jamais par le même `OwnerUser` que `requested_by`)

`Reclamation.status` :
`open → in_progress → resolved` ou `→ rejected` ; `resolved`/`rejected → reopened` si le citoyen n'est pas satisfait de la réponse, dans un délai limité (voir `notifications.md` §6).

## 4. Isolation multi-tenant (BOLA)

- Toutes les tables ci-dessus portant `tenant_id` (`DocumentRequest`, `Transaction`, `Document`, `SigningKey`, `AdminAgent`, `VerificationLog.verifying_administration_id`, `Reclamation.handled_by` quand géré par un tenant) sont protégées par une policy PostgreSQL Row-Level Security filtrant sur le `tenant_id` du contexte de session — jamais seulement par un `WHERE` applicatif (voir `security.md` §2 et §4).
- Chaque nouvel endpoint manipulant une de ces entités doit être couvert par un test automatisé d'accès croisé entre deux tenants factices avant merge (voir `security.md` §4).
- `OwnerUser`, `PlatformAuditLog`, `OwnerApprovalRequest`, `SigningKey` de type `platform_root` et `RevocationEntry` n'ont pas de `tenant_id` : ce sont les seules entités visibles transversalement, exclusivement via le rôle Owner. Une `Reclamation` de catégorie `fraud_suspicion` ou sans `document_request_id` identifiable est également visible par le Owner Backoffice (voir `notifications.md` §6).
