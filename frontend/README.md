npm --version     # should be v9+
git --version

# Frontend Setup Guide (Simplified)

## Prerequisites

- Node.js 18+
- npm 9+
- Git
- Backend services running ([Backend Setup](../backend/README.md))

## 1. Install Dependencies

```bash
cd esd-hdb/frontend
npm install
```

## 2. Configure Environment

Ensure the backend/.env file contains all required `VITE_*` variables, e.g.:

```
VITE_API_GATEWAY_URL=http://localhost:8000
VITE_SINGPASS_URL=http://localhost:8000
VITE_SINGPASS_USE_SESSIONS=true
VITE_PROCESS_BALLOT_API_KEY=ballot-cron-job-secret
```

## 3. Start Development Server

```bash
npm run dev
```

Open http://localhost:5173 in your browser.

---

For backend setup, see ../backend/README.md

## Development Guide

### Project Structure

```
frontend/
├── src/
│   ├── components/      # Vue components (buttons, forms, etc.)
│   ├── views/           # Page components (login, dashboard, ballot, etc.)
│   ├── router/          # Vue Router configuration
│   ├── stores/          # Pinia state management
│   ├── utils/           # Helper functions
│   ├── api/             # API client setup & endpoints
│   ├── App.vue          # Root component
│   └── main.ts          # Entry point
├── index.html           # HTML template
├── vite.config.ts       # Vite configuration
├── package.json         # Dependencies
├── tsconfig.json        # TypeScript configuration
└── .env                 # Environment variables (reads from ../backend/.env)
```

### Key Files to Know

| File | Purpose |
|------|---------|
| `src/main.ts` | Application entry point |
| `src/App.vue` | Root layout component |
| `src/router/index.ts` | Page routes & navigation |
| `src/api/` | API client configuration |
| `src/stores/` | Global state management |
| `vite.config.ts` | Dev server & build settings |

### Available Scripts

```bash
npm run dev        # Start development server (http://localhost:5173)
npm run build      # Build for production (creates dist/)
npm run preview    # Preview production build locally
npm run lint       # Check code quality with ESLint
npm run format     # Auto-format code with Prettier
npm run type-check # TypeScript type checking
```
