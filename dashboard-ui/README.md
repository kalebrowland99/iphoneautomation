# Farm dashboard UI (React + shadcn)

Optional React build that mirrors the Acme Hero design. The live dashboard is **server-rendered** at `src/imouse_farm/dashboard/templates/index.html` with Tailwind CDN — no Node required.

When Node.js is installed, you can build this package and serve from `src/imouse_farm/dashboard/static/dist/`.

## Setup

```bash
cd dashboard-ui
npm install
npx shadcn@latest init   # if not already configured
npm run build
```

Copy build output:

```powershell
Remove-Item -Recurse -Force ..\src\imouse_farm\dashboard\static\dist -ErrorAction SilentlyContinue
Copy-Item -Recurse dist ..\src\imouse_farm\dashboard\static\dist
```

## Components

- `components/ui/acme-hero.tsx` — nav + hero shell (from 21st.dev)
- `components/ui/button.tsx`, `sheet.tsx`, `separator.tsx`, etc. — shadcn primitives

Wire the farm run console (progress bar, unified log, slot picker) into a page that wraps `AcmeHero` or replace the hero section with farm-specific copy.
