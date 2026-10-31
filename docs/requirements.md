# Exigences — DocuCiv

## 1. Acteurs

- **Citoyen / Entreprise** : demandeur de document administratif
- **Administration émettrice** : ministère/mairie qui produit et signe le document
- **Administration requérante** : entité qui vérifie un document présenté
- **Opérateur plateforme (DocuCiv)** : exploite le SaaS, gère les abonnements et le support

## 2. User stories

### Administration émettrice
- En tant qu'agent, je consulte la file des demandes en attente de revue pour mon administration (tenant), avec la photo/scan jointe par le citoyen et l'identifiant du document de référence.
- En tant qu'agent, je peux accepter ou rejeter une pièce justificative (avec motif) avant que la production du document ne démarre.
- En tant qu'agent, je peux générer le document numérique final **au format PDF** (acte de naissance, certificat de résidence, CAR, permis de conduire, etc.) à partir d'un gabarit, une fois la pièce justificative acceptée et le paiement confirmé.
- En tant qu'administration, chaque document PDF que j'émets reçoit une signature cryptographique unique et un horodatage certifié, afin de garantir son intégrité.
- En tant qu'administration, un QR code de sécurité lié à la signature est intégré directement dans le PDF de chaque document.
- En tant qu'administration, je peux connecter mon système existant via une API d'intégration plutôt que ressaisir les données.

### Citoyen / Entreprise
- En tant que citoyen, je peux demander un document en ligne via un formulaire simplifié (web ou mobile), en indiquant l'identifiant du document existant concerné (ex. numéro de l'ancien acte à renouveler).
- En tant que citoyen, **je suis informé immédiatement si le document que je référence n'existe pas** chez l'administration émettrice, avant qu'on me demande de payer.
- En tant que citoyen, je peux joindre une photo/scan du document existant à l'appui de ma demande (pièce justificative), prise directement depuis l'appareil ou importée depuis la galerie.
- En tant que citoyen, **je suis informé si ma photo n'est pas correcte** (illisible, mauvais format, incohérente) avec le motif précis, et je peux la soumettre à nouveau.
- En tant que citoyen, je peux payer les frais via Mobile Money (Orange Money, MTN MoMo, Moov Money).
- En tant que citoyen, **je suis notifié dès que mon paiement est reçu et confirmé**, et informé si le paiement échoue pour pouvoir réessayer.
- En tant que citoyen, **je suis informé que mon document est en cours de traitement, avec un délai estimé** (ex. "entre 2 et 5 jours ouvrés").
- En tant que citoyen, **je suis notifié dès que mon document est créé**, avec un lien sécurisé pour le télécharger.
- En tant que citoyen, **je suis notifié si ma demande est rejetée**, à n'importe quelle étape, avec le motif.
- En tant que citoyen, **je peux consulter à tout moment le statut de traitement de ma demande** (où j'en suis exactement), sans attendre une notification.
- En tant que citoyen, **je peux déposer une réclamation** à tout moment (délai anormal, erreur sur le document, problème de paiement, etc.) et suivre sa résolution.
- En tant que citoyen, je dispose d'un portefeuille numérique listant l'historique de mes documents PDF.
- En tant que citoyen, je peux transmettre (partager) mon document PDF à une administration requérante directement depuis la plateforme, avec un contrôle précis du destinataire, de la durée et du nombre d'usages du partage.
- En tant que citoyen, je peux révoquer un partage en cours si je change d'avis ou si je l'ai transmis par erreur.

### Administration requérante
- En tant qu'agent vérificateur, je reçois le document transmis par le citoyen (lien de partage ou transfert in-app) et j'accède directement au PDF et à son statut de vérification.
- En tant qu'agent vérificateur, je peux scanner le QR code intégré au PDF ou saisir un numéro de document pour vérifier instantanément : authenticité, intégrité, émetteur, dates d'émission/expiration.
- En tant qu'agent vérificateur, je peux imprimer une copie du document avec la mention "Vérifié numériquement".
- En tant qu'agent vérificateur, je peux consulter l'historique des vérifications effectuées sur un document.
- En tant qu'agent vérificateur en zone peu connectée, je peux vérifier la signature et le hash d'un document **sans réseau**, à partir d'un cache local de clés publiques/liste de révocation, avec un résultat marqué comme vérifié hors-ligne et resynchronisé dès reconnexion.

### Owner (opérateur de la plateforme DocuCiv)
- En tant qu'opérateur, je peux créer/suspendre un tenant (administration) et gérer son abonnement/tarification.
- En tant qu'opérateur, je supervise l'usage global (volumes d'émission/vérification, incidents paiement) via un backoffice dédié.
- En tant qu'opérateur, j'accède à cette plateforme avec SSO + MFA, jamais via les mêmes comptes que les administrations ou les citoyens.

### Citoyen (offline)
- En tant que citoyen sans connexion, je peux consulter les documents déjà téléchargés dans mon portefeuille (lecture seule).
- En tant que citoyen sans connexion, je peux préparer une demande de document ; elle est mise en attente et envoyée automatiquement dès que la connexion revient, sans duplication.
- En tant que citoyen, je ne peux pas payer ni recevoir de document signé hors-ligne — ces actions nécessitent une connexion.

## 3. Exigences non fonctionnelles

- **Performance** : vérification d'un document en moins de 3 secondes.
- **Disponibilité** : service critique (émission de documents officiels) — viser une haute disponibilité en production (hors MVP, cible à définir).
- **Sécurité** : TLS 1.3 en transit, AES-256 au repos, signatures non falsifiables (PKI/ECC, option blockchain).
- **Conformité** : loi ivoirienne sur la cryptographie/signature électronique, RGPD/CNIL Côte d'Ivoire.
- **Traçabilité** : chaque émission et chaque vérification est journalisée de façon immuable.
- **Accessibilité des paiements** : Mobile Money couvrant 90 %+ de la population cible.
- **Interopérabilité** : API standardisée utilisable par plusieurs ministères/mairies sans développement spécifique par partenaire.
- **Multi-tenant** : isolation stricte des données entre administrations (tenants), supervision transverse réservée au rôle Owner.
- **Offline-first (lecture/vérification)** : consultation du portefeuille et vérification de signature doivent fonctionner sans réseau ; aucune opération d'écriture critique (paiement, émission) n'est permise hors-ligne.
- **Pièces justificatives** : upload de photo/scan limité en taille et en type MIME (validé côté serveur), stocké chiffré, jamais utilisé comme preuve d'authenticité à lui seul — seule la signature numérique du PDF final fait foi côté vérification.
- **Format de sortie unique** : tout document émis est produit en PDF ; pas d'autre format de sortie supporté au MVP.
- **Notification à chaque étape** : aucune transition d'état (succès ou échec) ne doit rester silencieuse pour le citoyen — voir `docs/notifications.md` pour la liste exhaustive des messages. Pas de paiement demandé avant confirmation d'existence du document référencé.
- **Suivi et réclamation** : le statut d'une demande doit être consultable en continu (pas seulement via notification), et un canal de réclamation doit toujours être disponible, avec SLA de réponse défini par catégorie (voir `docs/notifications.md` §6).

## 4. Hors périmètre (MVP)

- Intégration blockchain complète (option envisagée post-MVP, voir `architecture.md`).
- Impression certifiée physique à grande échelle (le MVP couvre la mention numérique, pas le circuit d'impression partenaire).
- Vérification en masse via API entreprise (prévue dans le modèle économique, mais pas dans le MVP initial).
