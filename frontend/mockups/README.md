# Saaf Baat Frontend Mockups (Static)

These mockups are static HTML/CSS to quickly validate the **look & feel** and the **information hierarchy** against the current backend API.

## Open

- Open `frontend/mockups/home.html` in a browser
- Open `frontend/mockups/story.html` in a browser

## Backend Contract (Current)

- Feed cards: `GET /api/feed`
  - `story_id`, `created_at`, `headline`, `snippet`, `category`, `impact_labels`, `confirmed_facts`, `debated_claims`, `sources[]`
- Story detail: `GET /api/stories/{cluster_id}`
  - Everything in feed card + `articles[]` with `{source, headline, url, publish_date}`

The mockups render from `frontend/mockups/mock-data.js` but are shaped to match those DTOs.

