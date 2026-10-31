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

Restant pour clore la Phase 0 :
- Protection des branches `integration`/`main` sur l'hébergeur Git (à configurer côté plateforme — pas du code, voir note ci-dessous)
- Environnements dev/staging/prod séparés + coffre de secrets (Vault/Secrets Manager + Codemagic) réellement provisionnés

### Protection de branches

`docs/workflow.md` impose : pas de commit direct sur `integration`/`main`, tout passe par PR. Ceci est une configuration de l'hébergeur Git (ex. GitHub branch protection rules), pas du code — à activer manuellement sur le repo distant par un mainteneur ayant les droits admin.
