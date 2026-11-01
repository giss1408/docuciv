# Spécification API (draft) — DocuCiv

Toutes les routes sont servies derrière l'API Gateway (FastAPI), préfixées par `/api/v1`. Authentification par JWT/OIDC (citoyen/entreprise, agents d'administration) ou clé API + mTLS optionnel (intégrations systèmes). TLS 1.3 obligatoire.

Toute route de création accepte un header `Idempotency-Key` (requis pour les créations émises depuis une file offline resynchronisée) ; une requête rejouée avec la même clé retourne la réponse originale sans effet de bord supplémentaire.

## 1. Citoyen / Entreprise

### `POST /requests`
Crée une demande de document, avec référence au document existant. Déclenche le contrôle d'existence (`pending_reference_check`, voir `notifications.md` §3) **avant** de demander le paiement.
```json
// Request
{
  "administration_id": "uuid",
  "document_type": "acte_naissance",
  "reference_document_id": "AN-1998-004512",
  "payload": { "...": "champs du formulaire" }
}
// Response 201
{ "id": "uuid", "status": "pending_reference_check", "amount_due": 1000 }
```
Statuts possibles ensuite (notifiés automatiquement, voir `notifications.md` §2) : `reference_not_found` (échec terminal, pas de paiement demandé) ou `pending_payment` (document retrouvé, prêt pour upload de pièce + paiement).

### `POST /requests/{id}/evidence/upload-url`
Demande une URL pré-signée S3 pour téléverser la pièce justificative (photo/scan). Le fichier ne transite jamais par l'API applicative — upload direct client → S3.
```json
// Request
{ "mime_type": "image/jpeg", "file_size_bytes": 2400000 }
// Response 201
{ "evidence_id": "uuid", "upload_url": "https://...", "upload_fields": { "key": "...", "policy": "..." }, "expires_in": 300 }
// POST multipart vers upload_url avec upload_fields puis le fichier (POST pré-signé: S3 applique
// la taille max et le Content-Type exact).
```

### `POST /requests/{id}/evidence/{evidence_id}/complete`
Confirme la fin de l'upload côté client ; le backend vérifie la présence du fichier sur S3, son type réel (pas seulement l'extension), calcule le hash SHA-256 et passe `SourceEvidence.review_status = pending`.
```json
// Response 200
{ "evidence_id": "uuid", "content_hash": "sha256:...", "review_status": "pending" }
```

### `POST /requests/{id}/pay`
Initie le paiement Mobile Money.
```json
// Request
{ "provider": "orange_money", "phone": "+225xxxxxxxxx" }
// Response 202
{ "transaction_id": "uuid", "status": "initiated" }
```

### `GET /requests/{id}`
Statut courant d'une demande, incluant le statut de revue de la pièce justificative (`evidence_review_status`), `rejection_reason` si applicable, et `estimated_ready_at`.
```json
// Response 200
{
  "id": "uuid",
  "status": "in_progress",
  "evidence_review_status": "accepted",
  "estimated_ready_at": "2026-11-02T00:00:00Z",
  "history": [
    { "to_status": "pending_reference_check", "changed_at": "2026-10-30T08:00:00Z" },
    { "to_status": "pending_payment", "changed_at": "2026-10-30T08:01:00Z" },
    { "to_status": "paid", "changed_at": "2026-10-30T08:05:00Z" },
    { "to_status": "in_progress", "changed_at": "2026-10-30T09:00:00Z" }
  ]
}
```

### `GET /requests`
Liste toutes les demandes du citoyen authentifié avec leur statut courant ("mes démarches", voir `notifications.md` §5).

### `GET /wallet/documents`
Liste des documents (PDF) du portefeuille numérique de l'utilisateur authentifié.

### `GET /documents/{id}/download`
Retourne une URL de téléchargement signée et à expiration courte vers le PDF final (jamais une URL S3 publique permanente).

### `POST /documents/{id}/share`
Crée un `DocumentShare` : transmet le PDF signé à une administration requérante désignée (ou génère un lien à usage limité).
```json
// Request
{ "recipient_administration_id": "uuid", "delivery_method": "in_app_transfer", "max_uses": 1, "expires_in": 3600 }
// Response 201
{ "share_id": "uuid", "share_token": "opaque-token", "expires_at": "2026-10-30T15:00:00Z" }
```

### `POST /documents/{id}/share/{share_id}/revoke`
Révoque un partage en cours avant son expiration/usage.

### `POST /reclamations`
Crée une réclamation, liée à une `DocumentRequest` si applicable (voir `notifications.md` §6).
```json
// Request
{ "document_request_id": "uuid", "category": "delay", "description": "Ma demande est en traitement depuis 10 jours, le délai annoncé était de 5 jours." }
// Response 201
{ "id": "uuid", "status": "open", "sla_response_due_at": "2026-11-01T00:00:00Z" }
```

### `GET /reclamations`
Liste les réclamations du citoyen authentifié avec leur statut.

### `POST /reclamations/{id}/reopen`
Rouvre une réclamation `resolved`/`rejected` si le citoyen n'est pas satisfait de la réponse (dans un délai limité).

## 2. Administration émettrice

### `GET /issuer/requests?status=in_review`
File des demandes en attente de revue de pièce justificative pour le tenant de l'agent connecté.

### `GET /issuer/requests/{id}/evidence`
Retourne une URL de consultation (courte durée) de la pièce justificative pour revue par l'agent — jamais un accès S3 direct.

### `POST /issuer/requests/{id}/evidence/{evidence_id}/review`
Accepte ou rejette la pièce justificative (`SourceEvidence.review_status`) ; fait transitionner `DocumentRequest.status` vers `in_progress` (accepté) ou `rejected` (refusé, avec motif stocké à la fois dans `SourceEvidence.review_notes` et `DocumentRequest.rejection_reason`).
```json
// Request
{ "decision": "accepted" }
// ou
{ "decision": "rejected", "review_notes": "Photo illisible, numéro de document non identifiable" }
```

### `POST /issuer/documents`
Génère et signe le **PDF final** pour une `DocumentRequest` dont la pièce justificative a été acceptée (`in_progress`). Le backend compose le PDF (gabarit + données), insère le QR code, puis signe.
```json
// Request
{ "document_request_id": "uuid", "content": { "...": "contenu final du document" } }
// Response 201
{
  "document_id": "uuid",
  "format": "pdf",
  "content_hash": "sha256:...",
  "signature": "base64:...",
  "qr_code_token": "opaque-token",
  "pdf_download_url": "https://... (signée, courte durée)",
  "issued_at": "2026-10-30T12:00:00Z"
}
```

### `POST /issuer/documents/{id}/revoke`
Révoque un document émis par erreur (crée une `RevocationEntry`).

### `GET /issuer/reclamations`
File des réclamations liées aux demandes du tenant de l'agent connecté.

### `POST /issuer/reclamations/{id}/respond`
Répond à une réclamation (`status = resolved`/`rejected`), déclenche la notification au citoyen.
```json
{ "status": "resolved", "response": "Délai supplémentaire dû à une vérification manuelle du dossier. Document émis ce jour." }
```

## 3. Administration requérante

### `GET /shares/{share_token}`
Ouvre un document transmis via `DocumentShare` : retourne les métadonnées du document et une URL de téléchargement du PDF à usage limité (consomme `use_count`, refuse si `max_uses` atteint, expiré ou révoqué).

### `GET /verify/{qr_code_token}`
Vérifie un document via son jeton QR (lu depuis le PDF reçu, directement ou via partage).
```json
// Response 200
{
  "result": "valid",
  "document_type": "acte_naissance",
  "issuer": "Mairie d'Abidjan",
  "issued_at": "2026-10-30T12:00:00Z",
  "expires_at": null
}
```

### `POST /verify/by-reference`
Vérifie via numéro de document saisi manuellement.
```json
{ "document_number": "DC-2026-000123" }
```

### `GET /verify/{document_id}/history`
Historique des vérifications d'un document (droits restreints à l'émetteur et aux requérantes concernées), inclut le champ `mode` (`online`/`offline`).

### `GET /verify/offline-bundle`
Télécharge le paquet de vérification hors-ligne : clés publiques de tous les émetteurs actifs + liste de révocation (CRL) courante, signé par la plateforme. Utilisé par l'Admin Portal pour vérifier localement sans réseau. Cache client avec expiration courte (ex: 24h) pour limiter le risque d'utiliser une CRL périmée.
```json
// Response 200
{
  "generated_at": "2026-10-30T00:00:00Z",
  "expires_at": "2026-10-31T00:00:00Z",
  "issuer_keys": [{ "administration_id": "uuid", "public_key": "base64:..." }],
  "revoked_document_ids": ["uuid", "..."],
  "bundle_signature": "base64:..."
}
```

### `POST /verify/offline-log-sync`
Resynchronise les vérifications effectuées hors-ligne par un agent (batch). Idempotent par `local_id` fourni par le client.
```json
{
  "entries": [
    { "local_id": "uuid", "document_id": "uuid", "result": "valid", "verified_at_local": "2026-10-29T08:00:00Z" }
  ]
}
```

## 4. Citoyen — synchronisation offline

### `POST /requests/sync-batch`
Soumet en une fois les `DocumentRequest` créées hors-ligne par le Customer App (depuis l'`OfflineOutbox` local). Chaque entrée porte son `local_id` comme clé d'idempotence ; les doublons déjà synchronisés sont ignorés sans erreur. Note : la pièce justificative (`SourceEvidence`) n'est **jamais** mise en file offline — l'upload (photo) nécessite une connexion active via `/requests/{id}/evidence/upload-url` ; seul le formulaire texte de la demande peut être préparé hors-ligne.
```json
// Request
{ "requests": [ { "local_id": "uuid", "administration_id": "uuid", "document_type": "acte_naissance", "reference_document_id": "AN-1998-004512", "payload": {} } ] }
// Response 200
{ "results": [ { "local_id": "uuid", "server_id": "uuid", "status": "created", "evidence_required": true } ] }
```

## 5. Owner Backoffice

### `POST /owner/tenants`
Crée un nouveau tenant (administration).

### `POST /owner/tenants/{id}/suspend`
Suspend un tenant (coupe l'accès API/Admin Portal sans supprimer les données).

### `GET /owner/usage`
Métriques d'usage transverses (volumes d'émission/vérification, incidents paiement par tenant).

### `GET /owner/reclamations?category=fraud_suspicion`
File des réclamations à portée transverse (sans `document_request_id` identifiable, ou de catégorie `fraud_suspicion`/`payment_issue` touchant la plateforme) — voir `notifications.md` §6, journalisé dans `PlatformAuditLog`.

## 6. Webhooks

### `POST /webhooks/mobile-money/{provider}`
Reçoit la confirmation/échec de paiement des opérateurs (Orange Money, MTN MoMo, Moov Money). Signature du webhook vérifiée systématiquement avant traitement.

## 7. Codes d'erreur communs

| Code | Signification |
|---|---|
| 401 | Authentification manquante/invalide |
| 403 | Droits insuffisants (ex: administration non autorisée à vérifier ce document) |
| 404 | Ressource inconnue |
| 409 | Conflit d'état (ex: paiement déjà confirmé) |
| 422 | Payload de demande invalide |
