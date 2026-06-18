# Frontend (`@irp/frontend`)

TypeScript + React + Vite shell (AD-003). **Scaffold only** — a minimal shell proving the frontend builds. No dashboards,
no 1st/2nd Line views, no API calls, no domain functionality yet. Accessibility target is WCAG 2.1 AA for future UI.

## Commands

```bash
npm install                 # from repo root (workspaces)
npm run -w apps/frontend dev        # local dev server
npm run -w apps/frontend lint       # eslint
npm run -w apps/frontend typecheck  # tsc --noEmit
npm run -w apps/frontend test       # vitest
npm run -w apps/frontend build      # type-check + vite build
```

No calculation logic lives in the UI (ARCH-P-04); the UI will only render governed results from the backend.
