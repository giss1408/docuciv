# DocuCiv

Plateforme SaaS de sécurisation des documents administratifs en Côte d'Ivoire. Voir [`concept.md`](./concept.md) et [`AGENTS.md`](./AGENTS.md) pour le contexte complet et les règles de travail.

## Structure du dépôt

- [`docs/`](./docs) — spécifications (architecture, modèle de données, sécurité, API, workflow, notifications, roadmap)
- [`backend/`](./backend) — API FastAPI (Python), multi-tenant via PostgreSQL RLS
- [`apps/customer_app/`](./apps/customer_app) — app Flutter citoyens/entreprises (iOS/Android/Web)
- [`apps/admin_portal/`](./apps/admin_portal) — app Flutter Web, agents des administrations (par tenant)
- [`apps/owner_backoffice/`](./apps/owner_backoffice) — app Flutter Web, équipe DocuCiv (super-admin)
- [`apps/docuciv_design_system/`](./apps/docuciv_design_system) — thème/composants partagés entre les 3 apps
- [`codemagic.yaml`](./codemagic.yaml) — pipelines de build/distribution des 3 apps Flutter

## État : Phase 0 — Fondations techniques

Voir [`docs/roadmap.md`](./docs/roadmap.md). Réalisé :
- Repo backend FastAPI avec structure multi-tenant (Alembic + policy RLS PostgreSQL de référence sur `admin_agents`)
- CI backend de base (lint, type check, scan de dépendances, tests, build Docker) — `.github/workflows/backend-ci.yml`
- 3 projets Flutter scaffoldés avec thème partagé (`docuciv_design_system`)
- `codemagic.yaml` : workflows `integration` (distribution interne) et `main` (soumission store) par app, voir `docs/workflow.md` §5

Les 3 apps Flutter + le package partagé ont été vérifiés (`flutter pub get`/`analyze`/`test`, Flutter 3.24.2) — tout passe.

### Durcissement sécurité backend

En plus du socle Phase 0, le backend a été durci (voir `backend/README.md` pour le détail) :
- Scaffold auth/RBAC (`app/core/auth.py`) : un principal `owner` ne peut jamais porter de `tenant_id`, un rôle tenant ne peut jamais en être dépourvu — vérifié par type, pas seulement par convention.
- **Bug réel trouvé et corrigé** : le rôle DB utilisé par l'app était superuser, qui contourne silencieusement Row-Level Security même avec `FORCE ROW LEVEL SECURITY`. Migration `0002` crée un rôle applicatif `docuciv_app` sans privilège et un rôle `docuciv_owner` (`BYPASSRLS`, audité) — `tests/test_rls_isolation.py` prouve maintenant, contre un vrai PostgreSQL, que le tenant A ne peut pas lire les lignes du tenant B.
- CORS strict, en-têtes de sécurité, limite de taille de requête, docs API désactivées en production, secrets refusés par défaut hors `dev`.
- `python-jose` (non maintenu, CVE ouvertes) remplacé par `PyJWT` ; `cryptography`/`starlette`/`fastapi`/`pytest` mis à jour — `pip-audit` ne rapporte plus aucune vulnérabilité connue.
- CI : scan de secrets (gitleaks), `pip-audit` bloquant, scan d'image Docker (Trivy), test BOLA/RLS exécuté sur chaque PR.

### Design system

`apps/docuciv_design_system` porte maintenant des tokens (couleurs, espacements, rayons), un thème Material 3 clair/sombre complet, et des composants réutilisables (`DocuCivStatusBadge`, `DocuCivEmptyState`, `DocuCivCard`, `DocuCivSectionHeader`). Volontairement **pas d'écrans métier** : les maquettes des parcours citoyen/admin/owner (Phase 1 de la roadmap) n'existent pas encore, donc les 3 écrans placeholder actuels consomment ce système visuel sans qu'on invente l'UX réelle à leur place.

Restant pour clore la Phase 0 :
- Protection des branches `integration`/`main` sur l'hébergeur Git (à configurer côté plateforme — pas du code, voir note ci-dessous)
- Environnements dev/staging/prod séparés + coffre de secrets (Vault/Secrets Manager + Codemagic) réellement provisionnés
- Maquettes Phase 1 avant tout écran métier réel (`docs/roadmap.md`)

### Protection de branches

`docs/workflow.md` impose : pas de commit direct sur `integration`/`main`, tout passe par PR. Ceci est une configuration de l'hébergeur Git (ex. GitHub branch protection rules), pas du code — à activer manuellement sur le repo distant par un mainteneur ayant les droits admin.
