# Ceremonio — Flask Prototype

The original prototype of **[Ceremonio](https://ceremonio.vercel.app)**, an event
planning app. This is the early, fully working Python/Flask version I built to validate
the idea before the project grew into a larger team effort.

![screenshot placeholder](https://placehold.co/900x500?text=Screenshots+coming+soon)

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

## Setup

```bash
pip install -r requirements.txt
python app.py       # http://localhost:5000
```

No environment variables are required to run locally (SQLite is used by default).
See `.env.example` for optional production config (a real database via
`DATABASE_URL`, a `SECRET_KEY`).

Run the test suite with:

```bash
pip install -r requirements-dev.txt
pytest
```

## Architectural decisions

- **Server-rendered monolith over an API + SPA split.** For a solo prototype, one
  Flask app rendering Jinja templates meant no separate frontend build step and a
  much faster path from idea to working page.
- **SQLite by default, swappable via `DATABASE_URL`.** Zero-config for local
  development, but a one-line env var change moves it to Postgres/MySQL for real
  hosting — no code changes needed (`app.py` normalizes the URL scheme itself).
- **Token-based public invite links** rather than requiring guests to create
  accounts — the RSVP flow needed to have zero friction for someone opening a link
  on their phone.
- **JSON import/export as the backup mechanism**, so a user's data was never
  fully locked into one deployment while the hosting story was still being figured out.

## Folder structure

```
app.py                 # all routes + models (guests, groups, expenses, etc.)
wsgi.py                 # production entrypoint (gunicorn)
templates/              # Jinja templates, one per page (base.html is the shared layout)
static/                 # CSS, service worker, manifest, icons
translations/           # el.json / en.json — flat key-value dictionaries
tests/                  # pytest smoke tests (every page renders, PWA assets valid)
tools/                  # one-off scripts (e.g. icon generation)
DEPLOYMENT.md            # PythonAnywhere hosting guide
```

## Future improvements

This prototype is frozen as a historical snapshot — active development continues on
the [Next.js rewrite](https://github.com/Blizzard02/ceremonio-showcase). If it were
continued instead, the natural next steps would have been:

- Splitting `app.py` into blueprints as it grew past one file
- Real-time sync between partners (this version is single-editor, refresh-to-see-updates)
- A proper migrations tool instead of hand-editing the schema

## Why it became a React/Next.js app

This Flask version proved the idea worked end-to-end — guests, RSVPs, budgeting,
invitations, all in one place. As the project grew (more features, a team, a proper
product direction), it was rebuilt as **Ceremonio**, a Next.js/React app with a
Supabase backend, now live at [ceremonio.vercel.app](https://ceremonio.vercel.app).
The rewrite gave better mobile UX, real-time sync between partners, and a cleaner
foundation to keep building on — this repo is kept public as a snapshot of where it
started.
