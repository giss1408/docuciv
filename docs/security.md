# Sécurité & conformité — DocuCiv (in-depth)

Document de référence sécurité. Toute implémentation touchant signature, paiement, authentification ou accès aux documents doit être évaluée contre ce document avant merge.

## 1. Modèle de menaces (STRIDE)

| Catégorie | Menace concrète | Contre-mesure |
|---|---|---|
| **Spoofing** | Agent se faisant passer pour un autre tenant ; faux webhook Mobile Money | OIDC + scopes par tenant ; vérification de signature HMAC sur chaque webhook, rejet si absente/invalide |
| **Tampering** | Modification d'un PDF après émission ; rejeu d'un QR code modifié | Hash SHA-256 signé ; toute modification invalide la signature ECC, détectée à la vérification |
| **Repudiation** | Administration niant avoir émis/révoqué un document | Signature non répudiable (clé privée sous contrôle exclusif du tenant côté HSM) + `PlatformAuditLog`/`VerificationLog` append-only, horodatage RFC 3161 |
| **Information disclosure** | Fuite de données personnelles (acte de naissance, CAR) entre tenants ; énumération de documents via l'endpoint de vérification public | Row-Level Security PostgreSQL stricte ; rate limiting + pas de réponse différenciée entre "non trouvé" et "non autorisé" sur `/verify/*` |
| **Denial of service** | Flood sur `/verify/*` (endpoint public) ou sur les webhooks paiement | Rate limiting par IP/clé API (Redis), WAF/CDN en amont, quotas par tenant, circuit breaker sur les intégrations Mobile Money |
| **Elevation of privilege** | Agent `verifier_agent` accédant aux fonctions d'émission ; faille IDOR entre tenants (BOLA) | RBAC strict par rôle (`issuer_agent`,`verifier_agent`,`tenant_admin`,`owner`), vérification systématique `tenant_id` sur chaque requête (pas seulement au login) — voir §4 |

### Risques spécifiques au domaine
- **Vol/altération d'identité administrative** (ex. clé privée d'un ministère compromise) → voir §3 "compromission de clé".
- **Abus Owner** (un employé DocuCiv accède aux documents d'un citoyen sans raison) → double contrôle et journalisation obligatoire, voir §6.
- **Fraude Mobile Money** (faux webhook de confirmation déclenchant une émission gratuite) → voir §5.
- **QR code volé/partagé en masse** (le lien contient-il un secret suffisant ?) → le `qr_code_token` est un jeton opaque haute entropie (≥128 bits), à usage de *lookup*, jamais la preuve elle-même : la preuve est la signature vérifiée côté serveur/offline-bundle, pas la simple présentation du jeton.
- **Pièce justificative falsifiée** (photo retouchée d'un faux document pour obtenir une réémission) → la photo n'est jamais une preuve cryptographique, seulement une aide à la revue humaine par l'agent émetteur ; tout document final reste soumis au même contrôle d'émission que sans photo (vérification manuelle du dossier côté administration, hors périmètre technique de la plateforme).
- **Upload malveillant** (fichier exécutable déguisé en image, image surdimensionnée en déni de service, EXIF contenant des données sensibles) → voir §2bis.
- **Partage de document détourné** (`DocumentShare` intercepté ou transmis à un tiers non prévu) → jeton de partage distinct du `qr_code_token`, usage/durée limités, révocable, jamais d'accès permanent par défaut (voir §9bis).

## 2. Sécurité applicative (OWASP API Security Top 10)

| Risque OWASP | Application DocuCiv |
|---|---|
| **BOLA (Broken Object Level Authorization)** | Risque n°1 ici : un agent tenant A ne doit jamais lire/modifier un `Document`/`DocumentRequest` du tenant B. Vérification systématique côté service (pas seulement au niveau DB), tests automatisés dédiés (fuzz des `id` entre tenants) |
| **Broken authentication** | JWT courte durée + refresh rotatif, détection de réutilisation de refresh token (indice de vol), verrouillage après N échecs |
| **Broken object property level auth** | Mass assignment interdit : les schémas Pydantic d'entrée n'exposent jamais `status`, `tenant_id`, `role` en écriture libre depuis le client |
| **Unrestricted resource consumption** | Pagination obligatoire, limites de taille de payload, timeouts, rate limiting par endpoint sensible (`/verify/*`, `/requests`) |
| **Broken function level authorization** | Les routes `/issuer/*`, `/owner/*` vérifient le rôle à chaque appel via middleware FastAPI (dependency injection), pas de contrôle uniquement côté frontend Flutter |
| **Unrestricted access to sensitive business flows** | Limitation du nombre de demandes/vérifications par identité (anti-bot/anti-scraping sur `/verify/by-reference`) |
| **SSRF** | Les webhooks entrants (Mobile Money) sont validés par signature, jamais utilisés pour déclencher un fetch d'URL arbitraire côté serveur |
| **Security misconfiguration** | Headers de sécurité (CSP, HSTS, X-Content-Type-Options) sur l'Admin Portal/Owner Backoffice (Flutter Web) ; CORS restreint aux origines connues ; pas de mode debug en production |
| **Improper inventory management** | Un seul backend versionné (`/api/v1`), dépréciation explicite documentée, pas d'endpoint "oublié" en staging accessible publiquement |
| **Unsafe consumption of APIs** | Réponses des API Mobile Money/opérateurs validées (schéma strict) avant tout traitement, jamais de déserialisation non contrôlée |

Validation des entrées : tous les payloads (y compris `payload: jsonb` des `DocumentRequest`) sont validés par schéma Pydantic strict avant stockage — pas de JSON libre non validé en base.

## 2bis. Upload de pièces justificatives (photo/scan du document existant)

- **Upload direct vers S3** via URL pré-signée, jamais de fichier transmis en base64 dans le corps d'une requête API (évite de saturer le backend applicatif avec des binaires).
- **Validation côté serveur après upload** (jamais seulement côté client) : type MIME réel du fichier (signature binaire, pas seulement l'extension), taille maximale, dimensions raisonnables pour une photo de document (anti déni-de-service par fichier surdimensionné/bombe de décompression).
- **Scan antivirus/malware** du fichier avant que `review_status` ne passe à `pending` et qu'il ne soit visible par l'agent émetteur.
- **Suppression des métadonnées EXIF** (géolocalisation, modèle d'appareil) à l'ingestion, avant stockage — l'EXIF n'a aucune valeur probante ici et constitue une fuite de données personnelles inutile.
- **Accès restreint** : seul l'agent du tenant émetteur ciblé peut consulter la pièce justificative (`GET /issuer/requests/{id}/evidence`), via URL signée à courte durée — jamais un accès S3 direct ou permanent, et jamais visible par une administration requérante (seul le PDF final signé l'est, via `DocumentShare`).
- **Rétention** : la pièce justificative n'a de valeur que pendant la phase de revue ; politique de rétention/suppression après émission (ou après rejet définitif) à aligner avec `security.md` §13 (minimisation RGPD/CNIL), sauf obligation légale de conservation côté administration.

## 3. Cryptographie & gestion des clés

- **Signature document** : ECC P-256 (ou supérieur), clé privée par tenant générée et utilisée exclusivement dans un HSM/KMS managé (AWS KMS, Google Cloud KMS, ou HSM physique si datacenter Abidjan) — jamais exportable en clair.
- **Hiérarchie de clés** :
  - Clé racine de la plateforme (signe le `offline-bundle` et atteste les clés publiques des tenants) — la plus protégée, cérémonie de génération documentée, quorum (ex. 3-of-5) pour toute opération sur cette clé.
  - Clé par tenant (signe les documents) — rotation planifiée (ex. annuelle) et rotation d'urgence en cas de compromission.
- **Rotation** : chaque rotation de clé tenant génère un nouvel enregistrement de clé publique ; les documents déjà émis restent vérifiables via l'historique des clés publiques (jamais de suppression d'une ancienne clé publique, seulement marquage `retired`).
- **Compromission de clé (procédure)** :
  1. Révocation immédiate de la clé compromise (statut `compromised`, propagée au `offline-bundle`/CRL dans la minute).
  2. Tous les documents signés avec cette clé après la date de compromission estimée sont marqués `under_review`.
  3. Notification aux tenants/administrations requérantes concernées.
  4. Ré-émission des documents affectés avec la nouvelle clé une fois la cause traitée.
- **Horodatage** : source RFC 3161 tierce (TSA) indépendante de l'infra applicative, pour que l'horodatage résiste à une compromission du backend lui-même.
- **Hash** : SHA-256 minimum ; algorithmes de signature et de hash revus annuellement (agilité cryptographique — pas d'algorithme en dur non remplaçable).

## 4. Isolation multi-tenant (BOLA — approfondi)

- **Row-Level Security PostgreSQL** activée sur toutes les tables portant `tenant_id`, policy basée sur le `tenant_id` du contexte de session, pas sur un simple `WHERE` applicatif (défense en profondeur si un filtre applicatif est oublié).
- **Tests d'isolation obligatoires** : suite de tests automatisés qui tente systématiquement l'accès croisé entre deux tenants factices sur chaque nouvel endpoint — doit échouer (403/404 indifférencié) avant tout merge.
- **Owner vs Tenant** : le rôle Owner utilise un chemin d'accès distinct (service séparé ou flag explicite + justification obligatoire loggée), jamais le même token qu'un usage "tenant normal" élevé en privilège.

## 5. Paiement Mobile Money

- Les webhooks de confirmation de paiement sont vérifiés par signature cryptographique du fournisseur avant tout traitement (jamais de confiance sur l'IP source seule).
- Aucun déblocage de document sans confirmation explicite `confirmed` du fournisseur — pas de simulation en production.
- **Idempotence stricte** : chaque transaction porte une clé d'idempotence ; un webhook rejoué (replay) ne doit pas créditer/débloquer deux fois.
- **Anti-fraude** : détection de motifs anormaux (même numéro de téléphone pour N demandes en peu de temps, montant incohérent avec le type de document) → mise en file de revue manuelle plutôt que blocage silencieux.
- Les identifiants d'API des opérateurs sont des secrets (Vault/Secrets Manager), jamais commités, rotation périodique, accès restreint par rôle technique.

## 6. Contrôles d'accès & séparation des pouvoirs

- Authentification citoyen : JWT courte durée + refresh token rotatif, MFA optionnel (recommandé pour les comptes entreprise).
- Authentification administration (Admin Portal) : OIDC + clé API pour intégrations machine-à-machine, restriction IP/plage si possible, rotation régulière des clés, **MFA obligatoire pour le rôle `tenant_admin`**.
- Authentification Owner (Backoffice) : SSO interne + **MFA obligatoire sans exception**, séparé des comptes citoyens/administrations.
- **Double contrôle (dual control)** sur les actions Owner à fort impact : suspension d'un tenant, révocation d'une clé racine, export massif de données — nécessite validation par un deuxième compte Owner (four-eyes principle).
- Toute action Owner est journalisée dans `PlatformAuditLog` (append-only, non supprimable même par un Owner) avec justification obligatoire pour tout accès en lecture aux données d'un tenant.
- Partage de document (citoyen → administration requérante) : lien à usage/durée limités (`expires_in`), révocable par le citoyen à tout moment, jamais un accès permanent par défaut.
- Verrouillage de compte après échecs d'authentification répétés (brute-force), avec notification à l'utilisateur concerné.

## 7. Chiffrement & protection des données

- **En transit** : TLS 1.3 uniquement (TLS 1.2 toléré en fallback contrôlé si un partenaire l'exige, jamais moins) sur toutes les connexions (API Gateway, webhooks, apps Flutter). Certificate pinning sur les apps mobiles Customer/Admin pour empêcher les attaques MITM via proxy/CA compromise sur l'appareil.
- **Au repos** : AES-256 pour les données sensibles en base (PII, clés API). Chiffrement des volumes PostgreSQL et des buckets S3 (SSE-KMS), clés de chiffrement distinctes des clés de signature document.
- **Sauvegardes** : backups PostgreSQL chiffrés avec une clé dédiée (pas la même que les données live), stockés dans une région/zone distincte, accès de restauration soumis à double contrôle, test de restauration trimestriel documenté.
- **Minimisation** : les champs `payload` des `DocumentRequest` ne stockent que les données strictement nécessaires au type de document ; pas de copie du document final en base (uniquement `pdf_storage_key` vers S3). Idem pour `SourceEvidence.file_storage_key` (jamais le fichier en base).
- **PII dans les logs** : les logs applicatifs/observabilité (OpenTelemetry, Grafana/Loki) ne contiennent jamais de PII en clair (nom, numéro de téléphone, national_id) — masquage/hash systématique avant émission du log.

## 7bis. Transmission de document (DocumentShare)

- Le `share_token` est distinct du `qr_code_token` du document : révoquer un partage n'invalide jamais le document lui-même, et compromettre un partage ne donne pas accès aux autres documents du citoyen.
- Usage et durée strictement bornés (`max_uses`, `expires_at`) ; par défaut, un partage est conçu pour un usage unique sauf choix explicite du citoyen.
- Toute consultation via `GET /shares/{share_token}` est journalisée (qui, quand, résultat) au même niveau que `VerificationLog`.
- Le citoyen reste maître de la révocation (`revoked_at`) à tout moment, y compris après un premier usage si `max_uses > 1`.
- Le canal de transmission recommandé est interne à la plateforme (`in_app_transfer` si l'administration requérante est aussi utilisatrice de l'Admin Portal) ; un lien externe (email/SMS) doit rester à usage/durée limités pour réduire le risque d'interception ou de retransmission incontrôlée.

## 8. Sécurité des applications Flutter (mobile/web)

- **Customer App / Admin Portal mobile** : détection root/jailbreak avec dégradation du mode offline sensible (pas de blocage total, mais avertissement et restriction des opérations à risque) ; stockage des secrets locaux exclusivement via `flutter_secure_storage` (Keychain/Keystore natif), jamais `shared_preferences` pour un secret.
- **Obfuscation** : build Flutter en mode `--obfuscate --split-debug-info` pour les builds de production (limite la rétro-ingénierie des clients mobiles).
- **Certificate pinning** : sur toutes les apps mobiles (pas sur Owner Backoffice, usage interne réseau contrôlé) pour les appels vers l'API DocuCiv.
- **Admin Portal / Owner Backoffice (Flutter Web)** : CSP stricte, pas d'inline scripts, cookies de session `HttpOnly`/`Secure`/`SameSite=Strict`, protection CSRF sur toute action mutative.
- **Mode offline (rappel sécurité, voir aussi §9)** : jamais de clé privée ni de capacité d'émission côté client ; le cache local (documents, bundle de vérification) est chiffré et effacé à la déconnexion du compte ou à la désinstallation.

## 9. Mode offline — sécurité (détail)

- **Stockage local (Customer App)** : documents et données personnelles en cache chiffré sur l'appareil (clé de chiffrement dans le Keychain/Keystore via `flutter_secure_storage`, données dans une base locale chiffrée). Effacement à la déconnexion/désinstallation.
- **Vérification offline (Admin Portal)** : repose uniquement sur le `offline-bundle` signé par la clé racine de la plateforme (clés publiques tenants + CRL) — jamais sur une clé publique non vérifiée localement. Expiration courte du bundle (ex. 24h) pour limiter la fenêtre d'utilisation d'une CRL périmée ; un document révoqué après téléchargement du bundle peut être transitoirement signalé `valid` en local, mais est requalifié et audité dès resynchronisation (`mode = offline` tracé dans `VerificationLog`).
- **Pas d'écriture critique offline** : aucune émission de document, aucune confirmation de paiement, aucune clé privée ne transitent ou ne sont générées côté client.
- **Idempotence de synchronisation** : toute donnée créée offline (`OfflineOutbox`, logs de vérification offline) est resynchronisée via une clé d'idempotence (`local_id`) pour éviter les doublons ou rejeux, avec détection d'anomalie si un même `local_id` revient avec un payload différent (possible tentative de manipulation).

## 10. Infrastructure & supply chain

- **Durcissement infra** : conteneurs non-root, images minimales scannées (Trivy/Grype) en CI, Kubernetes avec NetworkPolicies restrictives entre services, secrets jamais en variable d'environnement en clair dans les manifests (Vault/Secrets Manager + injection runtime).
- **Supply chain** : SBOM généré à chaque build, scan de dépendances (SCA) bloquant en CI sur vulnérabilités critiques/high, dépendances Python et packages Flutter/Dart figés (lockfiles) et revus périodiquement.
- **Secrets** : rotation régulière, jamais commités (pre-commit hook + scan secrets en CI type gitleaks), séparation stricte des secrets par environnement (dev/staging/prod).
- **Exposition réseau** : WAF/CDN devant l'API publique, segmentation réseau entre API Gateway, services internes et base de données (pas d'accès direct DB depuis l'extérieur).

## 11. Observabilité & réponse à incident

- **Détection** : alerting sur anomalies de sécurité (pics d'échecs d'authentification, pics de vérifications sur un même document, échecs de signature répétés, accès Owner hors plage horaire habituelle).
- **Plan de réponse à incident** : procédure documentée (détection → containment → éradication → notification → post-mortem), rôles définis, astreinte de sécurité pour les incidents critiques (compromission de clé, fuite de données).
- **Notification de violation** : procédure de notification des autorités compétentes (CNIL Côte d'Ivoire) et des personnes concernées en cas de fuite de données personnelles, dans les délais réglementaires applicables.
- **Rétention des logs d'audit** : conservation suffisante pour investigation (ex. ≥ 1 an pour `PlatformAuditLog`/`VerificationLog`), au-delà de la rétention fonctionnelle normale des autres données.

## 12. Continuité d'activité

- **Haute disponibilité** décrite dans `architecture.md` §6 ; ce document ajoute : la clé racine de signature de la plateforme doit avoir une procédure de reprise (recovery) distincte, testée, sans dépendre d'un unique opérateur.
- **Plan de reprise après sinistre (DR)** : objectifs RPO/RTO à définir avec le partenaire gouvernemental pilote avant mise en production ; restauration testée en environnement isolé (jamais directement en prod).

## 13. Conformité réglementaire

- **Loi ivoirienne sur la cryptographie et la signature électronique** : le mécanisme de signature doit être conforme aux exigences locales de signature électronique qualifiée — à valider juridiquement avant mise en production avec un partenaire gouvernemental.
- **RGPD / CNIL Côte d'Ivoire** : minimisation des données collectées, consentement explicite du citoyen pour le partage de documents, droit d'accès/suppression sur les données personnelles non réglementaires, registre des traitements, analyse d'impact (DPIA) pour les traitements à risque (documents d'identité).
- **Souveraineté des données** : si un partenariat gouvernemental l'exige, privilégier l'hébergement en datacenter local (Abidjan) plutôt que cloud régional ; dans ce cas, le HSM doit aussi être disponible localement (pas de dépendance à un KMS cloud étranger pour la clé racine).

## 14. Secure SDLC & vérification continue

- Revue de code obligatoire sur tout changement touchant auth, signature, paiement, isolation multi-tenant.
- Tests de sécurité automatisés en CI : tests d'isolation tenant (§4), tests d'authentification/autorisation, SCA (§10).
- **Pentest externe** avant toute mise en production avec un partenaire gouvernemental, puis cadence régulière (ex. annuelle) et après tout changement majeur d'architecture.
- **Bug bounty / canal de signalement responsable** à envisager une fois en production, pour permettre un signalement de vulnérabilité externe encadré.

## 15. Points à valider avant production (hors MVP)

- Audit de sécurité externe du service de signature et de la hiérarchie de clés (cérémonie de clé racine).
- Validation juridique de la conformité à la loi ivoirienne sur la signature électronique.
- Choix définitif PKI seule vs. ancrage blockchain complémentaire.
- Définition formelle des RPO/RTO et test du plan de reprise après sinistre.
- DPIA formelle avec le(s) partenaire(s) gouvernemental(aux) avant tout pilote impliquant des données d'état civil.
