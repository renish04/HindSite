# HindSite 🧠

![HindSite](src/assets/icons/ext-icon-128.png)

**HindSite is a Chrome extension that automatically remembers the pages you actually *read* — then lets you find them later by meaning, not exact keywords.**

Instead of manually bookmarking, HindSite watches your reading behavior (time on page, scroll depth, scroll speed). When a page crosses a "genuinely read" threshold, it saves the article's content and turns it into a vector embedding. Later, you press `Alt+C` and type something like *"that article comparing two databases"* — HindSite runs semantic search over everything you've read and surfaces the best matches.

---

## How it works

HindSite has two halves: a **Chrome extension** (capture + UI) and a **Python backend** (embeddings + semantic search).

**Capture (write path)**
1. A content script runs on every page and tracks active time, max scroll depth, and scroll velocity.
2. A page is saved when it looks genuinely read:
   - **Normal pages:** ≥ 60s active **and** ≥ 40% scrolled **and** the scroll was gradual (took > 10s to reach 40%, i.e. not skimming).
   - **Short pages:** ≥ 60s active time.
3. The main article text is extracted (Mozilla Readability), stored in `chrome.storage.local`, and sent through the background service worker to the backend.
4. The backend generates a 1024-dim embedding (Cohere) and stores the page + vector in PostgreSQL/pgvector. A page thumbnail is captured and stored too.

**Search (read path)**
5. `Alt+C` opens the quick-search bar; the query and your open tabs are sent to `POST /search`.
6. A lightweight router decides intent:
   - **Tab switch** — phrases like *"switch to / go to / open X"* match against your open tabs and jump to one.
   - **Semantic search** — everything else runs a **two-stage retrieval**: embed the query → pgvector cosine similarity (top ~20 candidates) → Cohere cross-encoder rerank → top 3 results.
7. Results render as cards (with thumbnails); clicking one opens the page.

---

## Tech stack

| Layer | Technology |
|---|---|
| Extension | Chrome MV3 (content script, service worker, popup), vanilla JavaScript |
| Content extraction | Mozilla Readability.js |
| Backend | Python, FastAPI, Uvicorn, SQLAlchemy, Pydantic |
| Database | PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) (`Vector(1024)`) |
| AI / retrieval | Cohere — `embed-english-v3.0` (embeddings) + `rerank-english-v3.0` (reranking) |

---

## Project structure

```text
/
├── manifest.json               # MV3 config, permissions, Alt+C command
├── src/
│   ├── content/                # Behavior tracking + content extraction (the "brain")
│   ├── background/             # Service worker: REST proxy + keyboard commands
│   ├── popup/                  # Toolbar popup: saved-pages list, delete/clear
│   ├── quicksearch/            # Alt+C search window
│   └── assets/                 # Icons
└── hindsite-backend/
    ├── app/
    │   ├── main.py             # FastAPI endpoints
    │   ├── models.py           # SQLAlchemy model (captured_pages)
    │   ├── schemas.py          # Pydantic request/response models
    │   ├── init_db.py          # One-time DB + pgvector setup
    │   └── services/           # embeddings, search (2-stage), intent router
    └── requirements.txt
```

---

## Setup

### Prerequisites
- Python 3.9+
- PostgreSQL with the **pgvector** extension (local, or a hosted DB like Neon/Supabase)
- A **Cohere API key** (free tier works) — https://dashboard.cohere.com

### 1. Backend

```bash
cd hindsite-backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create `hindsite-backend/.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/hindsite
COHERE_API_KEY=your_cohere_key_here
```

Initialize the database (enables pgvector + creates the table), then run the API:

```bash
python -m app.init_db
uvicorn app.main:app --reload --port 8000
```

The API runs at `http://localhost:8000` (interactive docs at `/docs`).

### 2. Extension

1. Open `chrome://extensions/` and enable **Developer mode**.
2. Click **Load unpacked** and select the repository root (the folder with `manifest.json`).
3. Browse normally — pages are saved automatically. Press **`Alt+C`** to search.

---

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/capture` | Save a page and generate its embedding |
| `POST` | `/search` | Tab-switch **or** semantic search |
| `POST` | `/pages/thumbnail` | Attach/replace a page thumbnail |
| `GET` | `/pages` | List recently captured pages |
| `DELETE` | `/pages/{id}` | Delete one page (by ID or URL) |
| `DELETE` | `/pages` | Delete all pages |
| `GET` | `/health` | Health check |

---

## Current status & limitations

This is an actively developed personal project. Where it stands today:

- **Local-first dev setup** — the extension points at a hardcoded `http://localhost:8000`; there's no deployed backend yet.
- **Rule-based intent router** — tab-switch vs. semantic search is decided by keyword patterns, not an LLM.
- **Vector search is an exact scan** — pgvector similarity runs without an ANN index (`HNSW`/`IVFFlat`), which is fine for a personal library but not tuned for millions of pages.
- **English-only** models (`embed-english-v3.0` / `rerank-english-v3.0`).
- **No automated tests** yet.

### Roadmap
- Configurable backend URL + a deployed instance
- ANN index on the embedding column for scale
- Optional LLM-based router / result summarization
- Multilingual embeddings

---

## License

MIT — see [LICENSE](LICENSE).
