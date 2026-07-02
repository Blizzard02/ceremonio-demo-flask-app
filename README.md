# Ceremonio — Flask Prototype

The original prototype of **[Ceremonio](https://ceremonio.vercel.app)**, a wedding/event
planning app. This is the early, fully working Python/Flask version I built to validate
the idea before the project grew into a larger team effort.

## What it does

- **Guests & groups** — add/edit/remove guests, organize them into groups
- **Reception planning** ("glenti") — plan the reception itself
- **Finances** ("oikonomika") — track budget and expenses, with an analytics view
- **Digital invitations** — a shareable public invite link (`/invite/<token>`) guests
  open to RSVP, with a live preview for the couple
- **Playlist** — collect song requests/preferences for the reception
- **Backup** — export/import all wedding data as JSON
- **Multi-wedding accounts** — switch between weddings owned by the same user
- **i18n** — Greek/English language switching
- **PWA** — installable, works offline, with a service worker

## Tech stack

- **Backend:** Flask, Flask-SQLAlchemy
- **Database:** SQLite locally, MySQL/Postgres in production (`DATABASE_URL` env var)
- **Frontend:** server-rendered Jinja templates, vanilla CSS/JS
- **Tests:** pytest — smoke tests covering every major page and the PWA setup
  (manifest, service worker, icons)
- **Deployment:** originally hosted on PythonAnywhere (see `DEPLOYMENT.md`)

## Why it became a React/Next.js app

This Flask version proved the idea worked end-to-end — guests, RSVPs, budgeting,
invitations, all in one place. As the project grew (more features, a team, a proper
product direction), I rebuilt it as **Ceremonio**, a Next.js/React app with a
Supabase backend, now live at [ceremonio.vercel.app](https://ceremonio.vercel.app).
The rewrite gave better mobile UX, real-time sync between partners, and a cleaner
foundation to keep building on — this repo is kept public as a snapshot of where it
started.

## Running it

```bash
pip install -r requirements.txt
python app.py       # http://localhost:5000
```

No environment variables are required to run locally (SQLite is used by default).
See `.env.example` for optional production config.
