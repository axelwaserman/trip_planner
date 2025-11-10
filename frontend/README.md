# Trip Planner Frontend

React + TypeScript frontend for the Trip Planner application.

## Tech Stack

- **React** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Chakra UI v3** - Component library
- **Framer Motion** - Animations (via Chakra)

## Development

**Install dependencies:**
```bash
cd frontend
npm install
```

**Run dev server:**
```bash
npm run dev
```

Frontend runs on http://localhost:5173

**Build for production:**
```bash
npm run build
```

## API Integration

API calls to `/api/*` are proxied to the backend (http://localhost:8000) during development. See `vite.config.ts` for proxy configuration.

## Project Structure

```
frontend/
├── src/
│   ├── App.tsx           # Main app component
│   ├── main.tsx          # Entry point with Chakra provider
│   └── ...
├── vite.config.ts        # Vite config with API proxy
├── tsconfig.json         # TypeScript config
└── package.json
```
