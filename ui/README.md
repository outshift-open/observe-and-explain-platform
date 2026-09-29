# OXP UI

The web frontend for **OXP** — an observability and analysis dashboard for multi-agent systems (MAS). It lets you browse applications, inspect individual sessions (execution graphs, agent conversations, reasoning paths, cost/latency metrics), and monitor live topology and semantic groups across agents.

## Tech stack

- [React 18](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- [Vite](https://vitejs.dev/) — dev server & build
- [React Router](https://reactrouter.com/) — routing (`src/routes`)
- [TanStack Query](https://tanstack.com/query) — server-state/data fetching (`src/api`, `src/provider`)
- [MUI](https://mui.com/) + [`@open-ui-kit/core`](https://www.npmjs.com/package/@open-ui-kit/core) — component library / design system
- [@antv/g6](https://g6.antv.antgroup.com/) and [@xyflow/react](https://reactflow.dev/) — graph visualizations (execution graphs, topology)
- [Zustand](https://github.com/pmndrs/zustand) — local UI state
- Yarn 4 (Berry) as the package manager

## Prerequisites

- Node.js `lts/iron` (Node 20.x) — see [`.nvmrc`](.nvmrc). If you use `nvm`, run `nvm use`.
- Yarn `4.5.0`, managed via the `packageManager` field / Corepack — no separate install needed if Corepack is enabled (`corepack enable`).
- A running instance of the OXP REST API (see the sibling `api` service) to point the UI at.

## Getting started

```bash
cp .env.sample .env
```

Fill in at least `VITE_REST_API_URL` in `.env` (see [Environment variables](#environment-variables) below), then:

```bash
yarn install
yarn dev
```

The dev server starts on [http://localhost:3000](http://localhost:3000) with hot module reload.

## Environment variables

All frontend env vars are consumed at build/dev time via `import.meta.env` and must be prefixed `VITE_`.

| Variable             | Description                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_REST_API_URL`  | Base URL of the OXP REST API (e.g. `http://localhost:8000/api/v1`). Used directly by API modules in `src/api/*`.                                              |
| `VITE_API_PROXY_URL` | Upstream URL the nginx container proxies `/rest` to in production (see [Docker / production build](#docker--production-build)). Not used in local `yarn dev`. |
| `VITE_FF_*`          | Feature flags — see below.                                                                                                                                    |

### Feature flags

Feature flags gate optional pages/sub-views on top of the always-on core features (Applications, Sessions, Metrics, Execution Graph). They're defined in [`src/config/featureFlags.ts`](src/config/featureFlags.ts) and read via the [`useFeatureFlag`](src/hooks/useFeatureFlag.ts) hook.

Resolution precedence (lowest to highest): built-in default → `VITE_FF_*` env var (build/dev-time) → `window.ff*` (runtime, injected per-deployment — see the Docker section).

| Flag key             | Env var                      | `window` property     | Default |
| -------------------- | ---------------------------- | --------------------- | ------- |
| `semantic_groups`    | `VITE_FF_SEMANTIC_GROUPS`    | `ffSemanticGroups`    | `true`  |
| `insights`           | `VITE_FF_INSIGHTS`           | `ffInsights`          | `true`  |
| `live_topology`      | `VITE_FF_LIVE_TOPOLOGY`      | `ffLiveTopology`      | `true`  |
| `stateful_eval`      | `VITE_FF_STATEFUL_EVAL`      | `ffStatefulEval`      | `true`  |
| `impact_assessment`  | `VITE_FF_IMPACT_ASSESSMENT`  | `ffImpactAssessment`  | `false` |
| `waste_estimation`   | `VITE_FF_WASTE_ESTIMATION`   | `ffWasteEstimation`   | `false` |
| `neurosymbolic_eval` | `VITE_FF_NEUROSYMBOLIC_EVAL` | `ffNeurosymbolicEval` | `false` |

`.env.sample` ships with explicit `true`/`false` values for every flag as a starting point — edit it to match what your local API instance actually supports.

## Available scripts

| Command                          | Description                                                           |
| -------------------------------- | --------------------------------------------------------------------- |
| `yarn dev` (alias: `yarn start`) | Run the app in development mode with HMR on port `3000`.              |
| `yarn build`                     | Type-check (`tsc`) then build the production bundle to `dist/`.       |
| `yarn preview`                   | Serve the production build locally for a quick smoke test.            |
| `yarn lint`                      | Run ESLint (`--fix`) and Prettier (`--write`) across the codebase.    |
| `yarn lint:check`                | Run ESLint and Prettier in check-only mode (used in CI / pre-commit). |
| `yarn format`                    | Run Prettier (`--write`) only.                                        |

A Husky `pre-commit` hook runs `lint-staged`, which applies `yarn lint` to staged `ts`/`tsx`/`js`/`jsx` files.

## Project structure

```
src/
├── api/          # Fetch functions + TanStack Query hooks per backend domain (oceApi, kgInspectorApi, metrics, ...)
├── assets/       # Icons, images
├── common/       # Cross-cutting constants, shared styles
├── components/   # Reusable UI + feature components (graphs, tables, cards, session views, ...)
├── config/       # Runtime config, e.g. featureFlags.ts
├── hooks/        # Shared React hooks (useFeatureFlag, ...)
├── pages/        # Route-level pages (Dashboard, Applications, ApplicationDetails, AgentDetailsPopulation, 404)
├── provider/     # App-wide providers (TanStack QueryClientProvider)
├── routes/       # Route path constants (PATHS) and route tree (routes.tsx)
├── store/        # Zustand stores
├── theme/        # Theming
├── types/        # Shared TypeScript types
└── utils/        # Pure helper functions
```

Most pages follow a tab-based pattern: a page component (e.g. `pages/ApplicationDetails`) owns a set of tabs, each backed by its own data-fetching hook and a dedicated component under `components/` (see `components/SessionDetails` for the session-level Overview / Analysis / Reasoning Path / Execution Graph / Conversation tabs).

## Docker / production build

The [`Dockerfile`](Dockerfile) is a two-stage build:

1. **Build stage** (`node:20-alpine`): `yarn install && yarn build`, producing static assets in `dist/`.
2. **Runtime stage** (`nginx:alpine`): serves the static bundle and uses nginx SSI (`ssi on;` in [`nginx.conf`](nginx.conf)) to inject per-deployment runtime config into `index.html` at container start — this is how `window.restApiUrl` and each `window.ff*` feature flag get set without rebuilding the image. [`entrypoint.sh`](entrypoint.sh) runs `envsubst` over `nginx.conf` using the container's environment before starting nginx.
3. `/rest` requests are proxied by nginx to `VITE_API_PROXY_URL`.

Run it locally with:

```bash
docker compose up -d
```

This builds the image and starts it per [`docker-compose.yml`](docker-compose.yml), exposing the app on [http://localhost:3000](http://localhost:3000) (mapped to container port `8080`) and reading env vars from your local `.env`.
