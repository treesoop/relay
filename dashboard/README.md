# Relay Dashboard

Next.js 16 App Router dashboard that browses the Relay commons. Deployed
on Vercel at [relay-dashboard-one.vercel.app](https://relay-dashboard-one.vercel.app).

## Pages

| Route | Purpose |
|---|---|
| `/` | Hero + top-confidence skills + latest entries + install block. |
| `/skills` | Full archive with search. `?q=...` runs semantic search against the commons. |
| `/skills/[id]` | Full skill reading view — problem / attempts timeline / body / metadata. |

## Design

Editorial / archival tone (Fraunces + IBM Plex Sans + JetBrains Mono, parchment
+ ink + burnt orange). The hero on each detail page is an **attempts
timeline** — every failed try with its reason struck through, the winning
attempt highlighted. This is Relay's unique asset so it gets the visual spotlight.

## Data fetching

All API calls run server-side via `lib/api.ts`. The API URL never reaches
the browser, which also sidesteps CORS. Each page uses ISR with a 60-second
revalidation window.

## Local dev

```bash
npm install
npm run dev         # localhost:3000
npm run build       # production build
```

Optional env:
- `RELAY_API_URL` — override the default App Runner URL.
- `RELAY_AGENT_ID` — override the default `dashboard-viewer` read-only id.

## Deploy

```bash
vercel deploy --prod
```

The project is linked to `dions-projects-f863aac6/relay-dashboard`.
