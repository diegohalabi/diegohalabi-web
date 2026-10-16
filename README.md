# Dr. Diego Halabi — Personal Portfolio

Personal portfolio of **Dr. Diego Halabi** — DDS, PhD in Medical Sciences, Head of the Department of Dentistry at Universidad Austral de Chile — integrating biomedical research, data science, and software engineering.

🔗 **Live site:** [diegohalabi.cl](https://diegohalabi.cl)

---

## Overview

A single-page, framework-free static portfolio. The publications and research grants are **synced automatically from ORCID** every week via a GitHub Actions cron job, so the site stays up to date without manual edits.

### Features

- ⚡️ **Static & dependency-free runtime** — one `index.html`, no client framework.
- 🌗 **Dark / light theme** — toggled and persisted in `localStorage`, with no flash of unstyled content (theme is applied before first paint).
- 🔄 **Automatic ORCID sync** — publications and grants are fetched weekly, normalized (author names, journal titles, DOI links) and committed to `data/` and `index.html`.
- 🔎 **Indexable content** — publications and grants are pre-rendered as static HTML, so they are visible to search engines and without JavaScript.
- 🔍 **Client-side search, year filter & pagination** over the pre-rendered publications (case- and accent-insensitive).
- 🛡️ **Safe sync** — the sync aborts without touching existing data if any ORCID request fails or a list suddenly shrinks; all rendered content is HTML-escaped and links are restricted to an `http/https/mailto` allowlist.
- 🏷️ **SEO & social** — canonical URL, Open Graph/Twitter cards, `Person` JSON-LD, favicon, `robots.txt` and `sitemap.xml`.
- 🎨 **Tailwind CSS** compiled and purged ahead of time (~27 KB), not loaded from a CDN.

---

## Tech stack

| Area | Tool |
|------|------|
| Markup | Static HTML (`index.html`) |
| Styling | Tailwind CSS v3 (CLI build) |
| Interactivity | Vanilla JavaScript (inline) |
| Data sync | Python + ORCID public API |
| Automation | GitHub Actions (weekly cron) |
| Hosting | Vercel (static) |

---

## Project structure

```
.
├── index.html              # The entire site (markup + inline JS; ORCID lists are generated)
├── css/
│   └── styles.css          # Compiled Tailwind output (committed build artifact)
├── src/
│   └── input.css           # Tailwind entry + custom styles (edit this, not css/styles.css)
├── tailwind.config.js      # Theme tokens (colors, fonts), content paths, darkMode: class
├── data/
│   ├── publications.json   # Auto-generated from ORCID
│   └── grants.json         # Auto-generated from ORCID
├── images/                 # Profile photo, WebP project images, OG image, icons
├── scripts/
│   ├── update_orcid.py     # Fetches ORCID data, writes data/*.json and renders it into index.html
│   └── compress_images.py  # Resizes/converts images to WebP
├── .github/workflows/      # ORCID sync workflow (weekly + manual dispatch)
├── package.json            # Tailwind build scripts
└── requirements.txt        # Python deps for the sync script
```

---

## Local development

### Prerequisites
- [Node.js](https://nodejs.org/) (for the Tailwind build)
- [Python 3.10+](https://www.python.org/) (only if running the ORCID sync locally)

### 1. Install dependencies

```bash
npm install
```

### 2. Build the CSS

The site links to `css/styles.css`, which is **generated** from `src/input.css`. Rebuild it whenever you change markup, classes, or the Tailwind config:

```bash
npm run build:css      # one-off minified build
npm run watch:css      # rebuild on change during development
```

> ℹ️ `css/styles.css` is a **committed build artifact** so Vercel can serve it statically with zero build config. Never edit it by hand — edit `src/input.css` or `tailwind.config.js` and rerun the build.

### 3. Serve the site

Open `index.html` directly, or via a local web server:

```bash
npx serve .
# or
python3 -m http.server 8000
```

---

## ORCID data sync

Publications and grants are pulled from the [ORCID public API](https://pub.orcid.org/), written to `data/publications.json` and `data/grants.json`, and rendered as static HTML into `index.html` between the `<!-- ORCID:* -->` markers (never edit those blocks by hand).

Name and journal corrections live in `AUTHOR_FIXES` and `JOURNAL_FIXES` at the top of `scripts/update_orcid.py`. The owner's name is unified as `Halabi D` and highlighted in author lists.

If ORCID fails or a list drops below 80% of its previous size, the script exits with an error and changes nothing. After intentionally removing works from ORCID, run it with `ALLOW_SHRINK=1`.

### Automatic
The workflow in `.github/workflows/` runs **every Sunday at 03:00 UTC** (and can be triggered manually from the Actions tab). It runs the Python script and commits any changes to `data/` and `index.html` with `[skip ci]`.

### Manual
```bash
pip install -r requirements.txt
ORCID_ID="0000-0002-1474-8066" python scripts/update_orcid.py
```

### Images
```bash
pip install Pillow
python scripts/compress_images.py SRC images/NAME.webp --max-width 1000
```
Then update the `<img>` `src`, `width` and `height` in `index.html`.

The ORCID iD is configurable via the `ORCID_ID` environment variable (defaults to the owner's iD).

---

## Deployment

The site is deployed on **Vercel** as a static site. Because the compiled CSS and synced JSON are committed to the repo, no build step is required on Vercel — it serves the files directly.

> The npm build script is named `build:css` (not `build`) on purpose, so Vercel does not attempt to run it automatically.

---

## License

© 2026 Dr. Diego Halabi. All rights reserved.
