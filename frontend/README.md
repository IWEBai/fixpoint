# Railo Frontend

Standalone React dashboard for the Railo security patch bot.

## Features

- **Analytics** — runs over time, fixes created/merged, CI success rate, fix-merge rate gauges
- **Run History** — enriched table with PR link, job status, fix PR link, relative timestamp
- **Repo Settings** — per-repo enable toggle, warn/enforce mode, max diff-lines/runtime sliders, `.fixpointignore` editor
- **Installations** — view all GitHub App installations
- **User Settings** — profile and notification preferences
- **OAuth login** — GitHub OAuth via backend session

## Tech Stack

- **React 18** + **TypeScript** (Vite)
- **Tailwind CSS** for styling
- **Recharts** for charts (BarChart, LineChart, RadialBarChart)
- **Lucide React** for icons
- **Axios** for API calls (base URL: `/api`, proxied to Flask backend)
- **Flask** backend (`webhook/server.py`) — JSON REST API + OAuth

## Development

```bash
npm install
npm run dev        # Vite dev server at http://localhost:5173
npm run build      # Production build → dist/
```

Set `VITE_API_URL` in `.env.local` to point at your local Flask server if needed:

```
VITE_API_URL=http://localhost:8000/api
```

## API endpoints consumed

| Endpoint                        | Purpose               |
| ------------------------------- | --------------------- |
| `GET /api/analytics/summary`    | Summary stats         |
| `GET /api/analytics/timeseries` | 30-day run chart data |
| `GET /api/runs`                 | Run history           |
| `GET /api/repos`                | Installation list     |
| `GET /api/repos/:id/settings`   | Repo settings         |
| `PUT /api/repos/:id/settings`   | Save repo settings    |
| `GET /api/user/settings`        | User profile          |
