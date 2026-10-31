# Notifications, gestion d'erreurs & réclamations — DocuCiv

Ce document définit **tous les messages envoyés au citoyen** à chaque étape du parcours (succès et échec), le mécanisme de suivi de statut à la demande, et le traitement des réclamations. Référence pour le service Notification (`architecture.md` §3) et pour `NotificationEvent`/`Reclamation` (`data-model.md`).

## 1. Principes

- **Un message à chaque transition d'état**, pas seulement au succès final — le citoyen ne doit jamais se demander "où en est ma demande ?" sans avoir reçu de notification.
- **Canal double** : email + SMS (le SMS est le canal de repli garanti, cohérent avec la couverture Mobile Money 90%+ visée, voir `requirements.md`) ; push notification in-app si le Customer App est installé.
- **Pas de PII sensible dans le corps du SMS** (limiter aux identifiants de suivi, pas de contenu de document) ; le détail complet est accessible via l'app/lien sécurisé.
- **Chaque notification est journalisée** dans `NotificationEvent` (canal, modèle utilisé, statut d'envoi, pas le contenu complet si sensible) pour permettre le support et l'audit.
- **Idempotence** : une notification ne doit jamais être envoyée deux fois pour le même événement (clé d'idempotence sur `(document_request_id, event_type)`), même en cas de retry du worker.

## 2. Messages par étape du parcours

| # | Étape | Déclencheur | Message au citoyen | Canal |
|---|---|---|---|---|
| 1 | Demande créée | `POST /requests` réussi, `status = pending_reference_check` | "Votre demande #{ref} a été enregistrée. Vérification du document de référence en cours." | in-app |
| 2a | **Document de référence introuvable** | Vérification du `reference_document_id` échoue, `status = reference_not_found` (voir §3) | "Nous n'avons pas pu retrouver le document {reference_document_id} auprès de {administration}. Merci de vérifier le numéro et de soumettre une nouvelle demande." | email + SMS |
| 2b | Document de référence trouvé | Vérification réussie, `status = pending_payment` | "Document retrouvé. Montant à payer : {amount} FCFA. Merci de joindre une photo claire du document, puis de procéder au paiement." | in-app |
| 3a | **Upload de pièce rejeté (technique)** | `POST /requests/{id}/evidence/{evidence_id}/complete` échoue la validation automatique (type/taille/antivirus, voir `security.md` §2bis) | "Votre photo n'a pas pu être traitée : {reason}. Merci de reprendre une photo nette, bien éclairée, montrant l'intégralité du document, dans un format supporté (jpg/png/pdf), et de la soumettre à nouveau." | email + SMS |
| 3b | Upload de pièce accepté (techniquement) | `POST .../complete` réussi, `SourceEvidence.review_status = pending` | "Votre photo a bien été reçue et sera examinée par {administration} lors du traitement de votre demande." | in-app |
| 4 | Paiement en attente | Reprise, rappel disponible dès `status = pending_payment` (étape 2b) | "Montant à payer : {amount} FCFA. Choisissez votre opérateur Mobile Money pour finaliser — vous pouvez payer avant ou après avoir joint votre photo." | in-app |
| 5a | **Paiement échoué** | Webhook opérateur `failed` ou timeout | "Le paiement de {amount} FCFA via {provider} a échoué. Vous pouvez réessayer." | email + SMS |
| 5b | **Paiement reçu** | Webhook opérateur `confirmed`, `status = paid` | "Paiement de {amount} FCFA confirmé. Votre demande #{ref} va être examinée par {administration}." | email + SMS |
| 6a | **Pièce justificative rejetée (revue humaine)** | `POST /issuer/requests/{id}/evidence/{evidence_id}/review` avec `decision = rejected`, `SourceEvidence.review_status = rejected`, `DocumentRequest.status = rejected` | "Votre demande #{ref} n'a pas pu être validée : {rejection_reason}. {Politique de remboursement si paiement déjà effectué.} Vous pouvez soumettre une nouvelle demande avec une photo corrigée." | email + SMS |
| 6b | Traitement démarré + délai estimé | `POST .../review` avec `decision = accepted`, `status = in_progress` | "Votre document ({document_type}) est en cours de préparation par {administration}. Délai estimé : {estimated_ready_at} (ex: 2 à 5 jours ouvrés). Vous serez notifié dès qu'il sera prêt." | email + SMS |
| 7a | **Demande rejetée en cours de traitement** | `DocumentRequest.status = rejected` depuis `in_progress` (ex. dossier incomplet découvert par l'administration) | "Votre demande #{ref} n'a pas pu être traitée : {rejection_reason}. Contactez le support si vous pensez qu'il s'agit d'une erreur." | email + SMS |
| 7b | **Document créé** | `POST /issuer/documents` réussi, `status = issued` | "Votre document est prêt ! Téléchargez-le en toute sécurité : {pdf_download_url}." | email + SMS + push |
| 8 | Document partagé (transmis) | `POST /documents/{id}/share` | "Votre document a été transmis à {recipient_administration}. Le lien expire le {expires_at}." | in-app |
| 9 | Document vérifié par le destinataire | `VerificationLog` créé pour ce document (optionnel, configurable par le citoyen — information potentiellement sensible, voir §6) | "{recipient_administration} a vérifié votre document le {verified_at}." | in-app (jamais SMS par défaut) |
| 10 | **Délai dépassé** | `estimated_ready_at` dépassé sans `issued`/`rejected` | "Votre demande #{ref} prend plus de temps que prévu. Nouveau délai estimé : {new_estimate}. Nous vous présentons nos excuses pour l'attente." | email + SMS, déclenché automatiquement (voir §4) |

Note sur l'ordre réel (paiement avant revue humaine) : conformément à `data-model.md` §3 (`pending_reference_check → pending_payment → paid → in_review → in_progress → issued`), **le paiement est confirmé avant que l'agent n'examine la pièce justificative**. L'upload (étape 3a/3b) n'est validé que techniquement à ce stade (format/taille/antivirus) ; la revue humaine par l'agent (étape 6a/6b) n'a lieu qu'une fois la demande `paid`, dans l'état `in_review`. Le citoyen peut uploader sa photo et payer dans l'ordre qu'il préfère, mais la demande ne passe en `in_review` qu'une fois les deux faits (évidence uploadée + paiement confirmé).

## 3. Contrôle d'existence du document avant paiement

Pour éviter de faire payer un citoyen pour un document de référence qui n'existe pas :

1. Dès la création de la `DocumentRequest` (`reference_document_id` renseigné), le backend interroge l'**API d'intégration de l'administration émettrice** (si disponible) ou met la demande en file de vérification manuelle rapide par un agent (si l'administration n'a pas d'API — cas attendu pour les tenants pilotes au MVP).
2. Statut intermédiaire `DocumentRequest.status = pending_reference_check` **avant** `pending_payment`.
3. Résultat :
   - **Trouvé** → passage à `pending_payment`, message 2b envoyé, le citoyen peut uploader sa pièce justificative puis payer.
   - **Introuvable** → `status = reference_not_found` (échec terminal, pas de paiement demandé), message 2a envoyé.
   - **Non vérifiable automatiquement** (pas d'API, tenant pilote) → bascule directe en `pending_payment` avec un avertissement in-app ("vérification manuelle lors du traitement — vous serez remboursé si le document n'existe pas", voir `security.md` §5 anti-fraude et politique de remboursement à définir par tenant) ; la vérification réelle a alors lieu en `in_review`/`in_progress` et peut encore produire un `rejected` avec remboursement.

**Règle stricte** : on ne demande jamais le paiement si le système a positivement déterminé que le document de référence n'existe pas.

## 4. Délais de traitement & relance automatique

- Chaque `document_type` a un délai de traitement cible configuré par tenant (ex. certificat de résidence : 2 jours ouvrés ; acte de naissance : 5 jours ouvrés) — table de configuration par administration, pas en dur dans le code.
- À l'entrée en `in_progress`, `estimated_ready_at` est calculé et communiqué (message 6b).
- Un job planifié (Celery beat) vérifie quotidiennement les demandes `in_progress` dont `estimated_ready_at` est dépassé → envoie le message 10 et notifie l'agent émetteur en charge (file de relance interne sur l'Admin Portal) pour éviter que des dossiers ne stagnent silencieusement.

## 5. Demande de statut à la demande (pull, en complément du push)

- `GET /requests/{id}` (déjà défini dans `api-spec.md`) retourne le statut courant, l'historique des transitions (horodaté), et `estimated_ready_at` si applicable — le citoyen peut consulter à tout moment sans attendre une notification.
- `GET /requests` liste toutes les demandes du citoyen avec leur statut courant (vue "mes démarches").
- Dans le Customer App, chaque demande affiche une **timeline** (créée → pièce validée → payée → en traitement → prête) reflétant exactement les étapes du §2, pas seulement un statut texte brut.

## 6. Réclamations

Un citoyen doit pouvoir signaler un problème à tout moment (délai anormal, document erroné, paiement prélevé sans suite, document reçu par erreur par une administration requérante, etc.).

### Modèle
Voir `Reclamation` dans `data-model.md`. Une réclamation est toujours liée à une `DocumentRequest` (ou, si aucune demande identifiable, créée en libre avec contexte texte).

### Flux
1. Citoyen : `POST /reclamations`, avec `document_request_id` optionnel (présent si liée à une demande précise), un motif (`category`) et une description libre (voir `api-spec.md` §1).
2. Message d'accusé de réception immédiat : "Votre réclamation #{ref} a été enregistrée, nous vous répondrons sous {sla_response_due_at} (ex: 48h)." Le SLA affiché dépend de la catégorie (voir §"Priorisation" ci-dessous) et est stocké sur la réclamation (`Reclamation.sla_response_due_at`, voir `data-model.md`).
3. La réclamation apparaît dans une file dédiée de l'**Admin Portal** du tenant concerné (`GET /issuer/reclamations`, si liée à une `DocumentRequest`) **ou** du **Owner Backoffice** (`GET /owner/reclamations`, si elle concerne la plateforme elle-même — paiement, bug applicatif, litige entre tenants, ou sans `document_request_id`).
4. Un agent/owner répond (`POST /issuer/reclamations/{id}/respond`, champ `response`, `status = resolved`/`rejected`) → notification au citoyen (email + SMS) avec la réponse.
5. Le citoyen peut consulter l'historique de ses réclamations (`GET /reclamations`), rouvrir une réclamation non résolue à sa satisfaction (`POST /reclamations/{id}/reopen`, `status = reopened`) dans un délai limité.

### Catégories de réclamation (`Reclamation.category`)
`delay` (délai anormal), `document_error` (erreur sur le document émis), `payment_issue` (paiement prélevé sans suite ou double prélèvement), `evidence_rejected_wrongly` (pièce justificative rejetée à tort), `fraud_suspicion` (suspicion d'usage frauduleux de son document), `other`.

### Priorisation
- `payment_issue` et `fraud_suspicion` sont traitées en priorité (SLA plus court, alerting dédié — voir `security.md` §11 observabilité/incident).
- Toute réclamation `fraud_suspicion` crée automatiquement une entrée d'investigation potentielle côté Owner (visibilité transverse justifiée, journalisée dans `PlatformAuditLog`).

## 7. Contraintes de sécurité sur les notifications (rappel, voir `security.md`)

- Les liens de téléchargement envoyés par email/SMS sont signés, à courte durée — jamais une URL S3 publique permanente.
- Aucune donnée personnelle sensible (contenu du document, numéro national d'identité) dans le corps d'un SMS ; uniquement dans l'app ou via un lien authentifié.
- `NotificationEvent` ne stocke pas le contenu complet d'un message contenant des PII — seulement les métadonnées nécessaires au support (type d'événement, canal, statut d'envoi, horodatage).
