# HindSite - GMM Classification Feature Removed

## Cleanup Complete ✓

All Gaussian Mixture Model (GMM) and topic classification features have been cleanly removed from the project.

### What Was Removed
1. **Backend Services**
   - `hindsite-backend/app/services/topic_model.py` - GMM clustering logic
   - `hindsite-backend/app/services/llm_refiner.py` - LLM refinement wrapper
   - `hindsite-backend/app/routers/topics.py` - Topic API endpoints

2. **Frontend Components**
   - `src/topics/` - Topic organization UI pages
   - `src/components/TopicView.css` - Dead component styles

3. **Documentation**
   - `docs/TOPIC_CLASSIFICATION.md` - Topic classification guide

4. **Models & Training**
   - `hindsite-backend/trained_models/` - Pickled GMM models

5. **Database Schema**
   - Removed topic_label, topic_confidence, topic_cluster_id, is_topic_outlier, topic_classified_at columns from models.py
   - Removed topic column migrations from main.py and init_db.py

---

## What Remains - Core Project

### Frontend (Chrome MV3 Extension)
- **Content Script** (`src/content/index.js`)
  - Passive engagement tracking: active time, scroll depth, scroll velocity
  - Readability-based content extraction with fallbacks
  - Thumbnail capture orchestration
  - In-page quick-search overlay with speech recognition

- **Background Service Worker** (`src/background/index.js`)
  - Message routing and coordination
  - Thumbnail capture (captureVisibleTab + in-page resize)
  - Backend sync
  - Tab switching detection

- **Popup** (`src/popup/index.html`, `src/popup/index.js`)
  - Saved pages list with stats
  - Delete/clear functionality

- **Quick Search Window** (`src/quicksearch/index.html`, `src/quicksearch/index.js`)
  - Quick search bar for restricted pages

### Backend (FastAPI + Postgres + pgvector)

**API Endpoints:**
```
GET  /health                    - Health check
POST /capture                   - Capture page with embedding
POST /search                    - Semantic search with reranking
GET  /pages                     - List captured pages
POST /pages/thumbnail           - Update thumbnail for a page
DELETE /pages/{page_id}         - Delete a page
```

**Services:**
- `embeddings.py` - Cohere embed-english-v3.0 vector generation
- `search.py` - Two-stage retrieval (pgvector + Cohere rerank)
- `router.py` - Intent detection (semantic_search vs tab_switch)

**Database:**
- PostgreSQL with pgvector extension
- Captured pages table with 1024-dim embeddings
- Thumbnail storage (BYTEA)

---

## Project Now Focused On

**Pure RAG System**: 
- Passive capture based on reading behavior (time + scroll depth)
- Semantic search with proper retrieval pipeline
- No topic classification / auto-organization
- Self-contained, honest engineering

**Stack:**
- Chrome MV3 extension
- FastAPI backend
- PostgreSQL + pgvector
- Cohere embeddings + reranking
- Docker Compose for local development

---

## Next Steps for You

1. **Deploy it** - Get it running on a real server (not localhost)
2. **Test the depth** - Be able to explain every choice: embeddings, pgvector, why rerank, why two-stage
3. **Document it** - Clean README with architecture diagram
4. **Use it** - Make yourself a real user of your own product
5. **Pair with DSA prep** - This is your project strength; DSA is the interview gate

