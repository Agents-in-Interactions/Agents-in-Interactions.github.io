# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static single-page website for the **"Agents in Interaction, from Humans to Robots"** workshop at CVPR 2025 (June 12, 2025, Nashville, TN). Hosted on GitHub Pages.

## Development

No build tools, package manager, or compilation step. The site is pure static HTML/CSS/JS.

**To preview locally:**
```bash
python3 -m http.server 8000
# or
npx serve .
```

## Repository Structure

- `index.html` — The entire website (single file, ~148 KB). All content is hardcoded here.
- `data/` — Static assets:
  - CSS: `bulma.min.css`, `fontawesome.all.min.css`, `academicons.min.css`, `index.css`, `style.css`
  - JS: `jquery.min.js`, `jquery.mobile.custom.min.js`, `modernizr.js`, `fontawesome.all.min.js`
  - Images: Speaker photos, teaser images, sponsor logos

## Architecture

**Single-file static site** using:
- **Bulma** — CSS grid/layout (`columns`, `is-max-desktop`, card components)
- **Font Awesome + Academicons** — Icons for social/academic links
- **jQuery** — Minimal DOM interaction
- **Google Fonts** — Castoro, Google Sans, Noto Sans

**Page sections** (linked via `#anchor` navigation):
1. Hero header with nav buttons
2. `#Motivation` — Workshop overview
3. `#speakers` — Invited keynote speakers (card grid with photos)
4. `#schedule` — Workshop timetable
5. `#call` / `#Papers` — Accepted/invited papers
6. `#organizers` — Workshop organizers
7. Footer — Sponsor logos (NVIDIA, Matterport)

## Content Updates

All content changes (speakers, schedule, papers, organizers) are made directly in `index.html`. Speaker images are stored in `data/` and referenced by filename. The Bulma responsive column classes (e.g., `is-one-quarter`) control speaker/organizer grid layout.
