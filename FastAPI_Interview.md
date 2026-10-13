# FastAPI Master Interview Guide: HindSite Backend
> **Target Role:** Specialist Programmer (SP) L1 — Infosys  
> **Project in Resume:** HindSite (AI-Powered Intelligent Browsing Assistant)  
> **Stack:** FastAPI, Uvicorn, Pydantic, SQLAlchemy, PostgreSQL, pgvector, Cohere Embeddings & Rerank

---

## Table of Contents
1. [The 60-Second Interview Elevator Pitch](#1-the-60-second-interview-elevator-pitch)
2. [FastAPI Architecture: The Three Pillars](#2-fastapi-architecture-the-three-pillars)
   - Uvicorn (ASGI Server)
   - Starlette (Routing, HTTP & Middleware)
   - Pydantic (Data Validation & Serialization)
   - ASGI vs WSGI Architecture
3. [The #1 Interview Trap: `def` vs `async def` Concurrency](#3-the-1-interview-trap-def-vs-async-def-concurrency)
4. [HindSite End-to-End Request Lifecycle & Flow Diagrams](#4-hindsite-end-to-end-request-lifecycle--flow-diagrams)
   - Architecture & Request Flow (Mermaid Diagram)
   - Flow 1: Ingestion Pipeline (`POST /capture`)
   - Flow 2: Unified Search Pipeline (`POST /search` - Tab Switch vs 2-Stage Vector Rerank)
5. [Complete FastAPI Concepts Breakdown (With HindSite Code)](#5-complete-fastapi-concepts-breakdown-with-hindsite-code)
   - Dependency Injection (`Depends` & `yield` generator)
   - Pydantic Schemas vs SQLAlchemy Models
   - Middlewares & CORS (Cross-Origin Resource Sharing)
   - Exception Handling (Global Handlers & `HTTPException`)
   - Route Modularization (`APIRouter`)
   - Auto-generated Docs (`/docs` Swagger & `/redoc`)
6. [Database & AI Engine Internals (PostgreSQL + pgvector + Cohere)](#6-database--ai-engine-internals-postgresql--pgvector--cohere)
   - Connection Pooling & Session Lifecycle
   - pgvector Cosine Distance (`<=>`)
   - Two-Stage Retrieval (Bi-Encoder Embeddings + Cross-Encoder Reranking)
7. [Minimalist Whiteboard Code Cheat-Sheet (2-Minute Code Snippets)](#7-minimalist-whiteboard-code-cheat-sheet-2-minute-code-snippets)
   - Snippet 1: Bare Minimum FastAPI App
   - Snippet 2: Pydantic Validation & Path/Query Parameters
   - Snippet 3: Database Session Dependency Injection (`get_db`)
   - Snippet 4: Complete Production-Grade CRUD Endpoint
8. [Infosys SP L1 Killer Q&A (Top 15 Tricky Questions & Model Answers)](#8-infosys-sp-l1-killer-qa-top-15-tricky-questions--model-answers)

---

## 1. The 60-Second Interview Elevator Pitch

> *"If an interviewer asks: 'Can you walk me through the backend architecture of your HindSite project?'"*

**Deliver this exact answer:**
> "HindSite is an AI-powered browsing memory extension backed by a high-performance **FastAPI** service. When a user browses, the extension captures DOM content, interaction metrics like scroll depth and time spent, and captured page thumbnails. 
> 
> The FastAPI backend serves two primary pipelines:
> 1. **Ingestion (`POST /capture`)**: Cleans DOM content, calls Cohere's `embed-english-v3.0` to generate 1024-dimensional semantic embeddings, and stores both raw metadata and vector embeddings in PostgreSQL using the `pgvector` extension.
> 2. **Unified Search (`POST /search`)**: An intelligent multi-intent query router first parses the query. If the user intends to switch tabs (e.g., 'switch to GitHub PR'), it performs high-speed lexical matching against open browser tabs. If it is an informational query, it executes a **Two-Stage Retrieval Pipeline**: first retrieving top candidates from PostgreSQL using `pgvector` cosine similarity, and then passing them through **Cohere Cross-Encoder Reranker** for precise semantic relevance before returning results.
>
> I chose FastAPI because of its asynchronous ASGI foundation, automated Pydantic schema validation, clean Dependency Injection for database sessions, and high throughput compared to traditional WSGI frameworks like Flask or Django."

---

## 2. FastAPI Architecture: The Three Pillars

FastAPI is not built from scratch; it is an orchestration of the best tools in the modern Python ecosystem:

```
+-----------------------------------------------------------+
|                     FastAPI Layer                         |
|   (Dependency Injection, OpenAPI/Swagger, Path Operations) |
+-----------------------------+-----------------------------+
|         Starlette           |          Pydantic           |
| (ASGI Framework, Routing,   |  (Data Validation, Parsing, |
|  Middlewares, WebSockets)   |    JSON Schema, Types)      |
+-----------------------------+-----------------------------+
|                       Uvicorn                             |
|          (ASGI Web Server: uvloop + httptools)            |
+-----------------------------------------------------------+
|                   Operating System (Sockets)              |
+-----------------------------------------------------------+
```

### Pillar 1: Uvicorn (The ASGI Server)
- **Role:** Listens on the network socket (e.g., `0.0.0.0:8000`), receives raw TCP packets, parses HTTP using `httptools` (C binding to Node.js HTTP parser), and hands requests to the ASGI application.
- Uses `uvloop` (an ultra-fast asyncio event loop written in Cython on top of `libuv`, the same C library powering Node.js).

### Pillar 2: Starlette (The Web Framework Engine)
- **Role:** Handles low-level web routing, request and response abstractions, HTTP cookies, headers, CORS middleware, session middleware, and WebSockets.
- FastAPI is literally a subclass of Starlette: `class FastAPI(Starlette)`.

### Pillar 3: Pydantic (Validation & Serialization)
- **Role:** Uses standard Python 3.10+ type hints to:
  1. **Parse & Validate:** Convert raw incoming JSON/form/query strings into strictly typed Python objects (rejecting malformed data with HTTP 422).
  2. **Serialize:** Convert Python objects/ORM models back into JSON responses matching `response_model`.
  3. **OpenAPI Spec:** Automatically generate JSON schemas for Swagger documentation.

---

### ASGI vs WSGI Architecture (Crucial for Infosys SP)

| Feature | WSGI (Flask, Django < 3.0) | ASGI (FastAPI, Starlette) |
| :--- | :--- | :--- |
| **Full Form** | Web Server Gateway Interface | Asynchronous Server Gateway Interface |
| **Model** | Synchronous, Blocking, Sequential | Asynchronous, Non-blocking, Event-driven |
| **Concurrency** | 1 request per thread/worker process | Thousands of concurrent connections per process |
| **Protocol Support**| HTTP/1.1 only | HTTP/1.1, HTTP/2, WebSockets, Long-polling |
| **I/O Wait** | Thread blocks while waiting for DB/API | Event loop yields to handle other requests |

```mermaid
graph TD
    subgraph WSGI_Model["WSGI (Flask): 1 Thread Per Request"]
        R1[Request 1] --> T1[Thread 1] --> DB1[(DB Query - Blocks Thread)]
        R2[Request 2] --> T2[Thread 2] --> DB2[(DB Query - Blocks Thread)]
        R3[Request 3] --> Wait[Queue / Blocked: Out of Threads!]
    end

    subgraph ASGI_Model["ASGI (FastAPI): Event Loop Concurrency"]
        AR1[Request 1] --> EL[Single Event Loop]
        AR2[Request 2] --> EL
        AR3[Request 3] --> EL
        EL -. "await I/O" .-> ADB[(Async DB / External API)]
        ADB -. "I/O Ready" .-> EL
    end
```

---

## 3. The #1 Interview Trap: `def` vs `async def` Concurrency

This is the most common test to identify whether someone truly understands FastAPI or just vibe coded it.

### The Question:
> *"In your `main.py`, I see you wrote:*
> ```python
> @app.post("/capture")
> def capture_page(page: PageCapture, db: Session = Depends(get_db)):
> ```
> *Why did you use standard `def` instead of `async def`? What happens internally if you change `def` to `async def` here?"*

### The Master Answer:
1. **How FastAPI handles normal `def`:**
   - FastAPI inspects the endpoint signature at startup.
   - If an endpoint is declared with standard **`def`**, FastAPI knows it contains **synchronous, blocking code** (like `psycopg2`, standard SQLAlchemy `Session`, or synchronous HTTP SDK calls).
   - FastAPI executes this function inside an external **Threadpool** (`anyio` worker threads).
   - Therefore, while the thread blocks waiting for PostgreSQL or Cohere, **the main ASGI event loop remains completely unblocked** and continues serving other incoming requests.

2. **The Disaster if you change it to `async def` without async drivers:**
   - If you write `async def capture_page(...)`, FastAPI assumes you will use non-blocking asynchronous calls (`await db.execute(...)`, `await cohere_client.embed(...)`).
   - FastAPI will run `async def` directly on the **main event loop thread**.
   - If you execute blocking code inside an `async def` endpoint (e.g., synchronous `db.query()` or `time.sleep()`), **you block the entire event loop**!
   - Every other user connected to the server will hang until that single database query or API call finishes.

3. **Rule of Thumb Summary:**
   - **Use `def`** if using synchronous libraries (standard `sqlalchemy`, `requests`, `psycopg2`).
   - **Use `async def`** ONLY if using asynchronous libraries with `await` (`httpx`, `asyncpg`, `aiofiles`, `AsyncSession`).

---

## 4. HindSite End-to-End Request Lifecycle & Flow Diagrams

### Complete System Architecture

```mermaid
sequenceDiagram
    autonumber
    actor User as Chrome Extension
    participant UV as Uvicorn (ASGI)
    participant MW as CORSMiddleware
    participant App as FastAPI Router
    participant Val as Pydantic Validation
    participant Dep as get_db (Depends)
    participant Svc as Services (Router / Search)
    participant Cohere as Cohere API
    participant PG as PostgreSQL (pgvector)

    User->>UV: HTTP POST /search {query, open_tabs}
    UV->>MW: Process HTTP Request & CORS Headers
    MW->>App: Match Route @app.post("/search")
    App->>Val: Validate JSON into SearchQuery model
    alt Validation Fails
        Val-->>User: 422 Unprocessable Entity
    end
    App->>Dep: Execute get_db() -> yield Session
    Dep-->>App: Injected active db: Session
    App->>Svc: query_router.detect_intent(query)
    
    alt Intent == "tab_switch"
        Svc-->>App: matched_tab (tab_id, confidence)
        App-->>User: 200 OK (query_type="tab_switch")
    else Intent == "semantic_search"
        App->>Svc: search_service.search_pages(query, db)
        Svc->>Cohere: embed(query, input_type="search_query")
        Cohere-->>Svc: 1024-dim Query Vector
        Svc->>PG: SELECT ... ORDER BY embedding <=> query_vector LIMIT 20
        PG-->>Svc: Top 20 Candidates
        Svc->>Cohere: rerank(query, candidates, top_n=3)
        Cohere-->>Svc: Top 3 Re-scored Documents
        Svc-->>App: List[PageResult]
        App-->>User: 200 OK (query_type="semantic_search")
    end

    App->>Dep: Exit scope: runs `finally: db.close()`
    Dep-->>PG: Return DB connection to pool
```

---

### Flow 1: Ingestion Pipeline (`POST /capture`)

1. **Client Request:** The Chrome Extension background script monitors tab activity. When a page has sufficient dwell time or user leaves, it bundles `{ url, content, metadata: {timeSpent, scrollPercent}, thumbnail }` and sends `POST /capture`.
2. **Pydantic Validation:** FastAPI validates the payload against `PageCapture(BaseModel)`.
3. **Deduplication Check:** `db.query(CapturedPage).filter_by(url=page.url).first()`.
   - If the page already exists, update the screenshot thumbnail if provided, and return early (`status: "exists"`).
4. **Text Cleaning:** `clean_content(content)` strips excessive whitespace and junk words longer than 50 characters.
5. **Vector Generation (Embedding):**
   - Calls `embedder.generate_document_embedding(content)`.
   - Uses Cohere `embed-english-v3.0` with `input_type="search_document"`.
   - Returns a 1024-dimensional float vector.
6. **Database Persistence:**
   - Constructs `CapturedPage` SQLAlchemy model.
   - Sets metadata: title, domain, time_spent, word_count, 1024-dim vector, thumbnail binary (`BYTEA`).
   - `db.add()`, `db.commit()`, `db.refresh()`.
7. **Cleanup:** `db.close()` runs via the dependency generator `finally` block.

---

### Flow 2: Unified Search Pipeline (`POST /search`)

```mermaid
flowchart TD
    Start([User sends query]) --> RouterCheck{QueryRouter: Intent?}
    
    RouterCheck -->|Starts with 'switch to', 'go to', 'open'| TabSwitch[Check Open Tabs]
    RouterCheck -->|Generic search phrase| VectorSearch[Semantic Search Pipeline]
    
    TabSwitch --> TabFound{Matching tab score >= 0.5?}
    TabFound -->|Yes| ReturnTab[Return TabSwitchResult: tab_id, window_id]
    TabFound -->|No fallback| VectorSearch
    
    subgraph TwoStageRetrieval["Two-Stage Retrieval Pipeline"]
        VectorSearch --> QEmbed[Cohere Embed: query -> 1024-dim vector]
        QEmbed --> PGVector[pgvector Cosine Search: <=> operator]
        PGVector --> Candidates[Retrieve Top 20 Candidates]
        Candidates --> Rerank[Cohere Cross-Encoder Rerank]
        Rerank --> TopK[Filter relevance_score > 0.001 -> Top 3]
    end
    
    TopK --> ReturnResults[Return SearchResponse with PageResults]
    Rerank -.->|API Failure / Timeout| Fallback[Fallback: Vector-only similarity >= 0.20]
    Fallback --> ReturnResults
```

---

## 5. Complete FastAPI Concepts Breakdown (With HindSite Code)

### 1. Dependency Injection (`Depends` & `yield`)

**What is it?**  
Dependency Injection (DI) allows you to declare external dependencies (like database sessions, current user, security tokens) directly in the path function parameters, without tightly coupling your business logic to resource creation.

**In HindSite (`app/database.py` & `app/main.py`):**
```python
# 1. Dependency Definition (app/database.py)
def get_db():
    db = SessionLocal()  # Acquire connection from pool
    try:
        yield db         # Inject into endpoint
    finally:
        db.close()       # Always executes after response is generated!

# 2. Dependency Usage (app/main.py)
@app.post("/capture")
def capture_page(page: PageCapture, db: Session = Depends(get_db)):
    # db is an active, isolated SQLAlchemy Session
    db.add(...)
    db.commit()
    # When this function returns, control resumes after 'yield' in get_db()
```

**Interview Gold:**
- **Why use `yield` instead of `return`?**  
  Because `yield` creates an **exit code block**. Code before `yield` runs *before* the request; code in `finally:` runs *after* the request completes—even if an exception was raised inside the endpoint! This prevents database connection leaks.

---

### 2. Pydantic Schemas vs SQLAlchemy Models

A classic fresher/SP trap is confusing Pydantic schemas with SQLAlchemy models.

| Characteristic | Pydantic Schema (`schemas.py`) | SQLAlchemy Model (`models.py`) |
| :--- | :--- | :--- |
| **Inherits From** | `pydantic.BaseModel` | `declarative_base()` |
| **Domain** | HTTP API Boundary (Input & Output) | Database Table Structure (Storage) |
| **Purpose** | Data validation, type coercion, JSON parsing | Object-Relational Mapping (ORM), SQL generation |
| **Lifecycle** | Exists in memory during request parsing/serialization | Persistent rows in PostgreSQL disk storage |

**Example from HindSite:**
- `PageCapture` (Pydantic): Validates incoming JSON from Chrome:
  ```python
  class PageCapture(BaseModel):
      url: str
      content: str
      metadata: dict
      thumbnail: Optional[str] = None
  ```
- `CapturedPage` (SQLAlchemy): Defines PostgreSQL schema with column constraints and indices:
  ```python
  class CapturedPage(Base):
      __tablename__ = "captured_pages"
      id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
      url = Column(String(2000), unique=True, index=True)
      embedding = Column(Vector(1024))
  ```

---

### 3. Middleware & CORS (Cross-Origin Resource Sharing)

**In HindSite (`app/main.py`):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Interview Explanation:**
- **What is CORS?** A browser security mechanism that restricts web pages or browser extensions from requesting resources from a different domain, port, or protocol.
- **Why HindSite needs it:** The Chrome extension runs under the origin `chrome-extension://<EXTENSION_ID>`, while FastAPI runs on `http://localhost:8000`. The browser sends an HTTP `OPTIONS` preflight request.
- `CORSMiddleware` intercepts the request before it reaches any route, adds `Access-Control-Allow-Origin: *`, and allows the browser to proceed with `POST /capture` or `POST /search`.

---

### 4. Exception Handling

FastAPI provides two primary layers of error handling:

1. **Operational/Business Logic Errors (`HTTPException`):**
   ```python
   page = db.query(CapturedPage).filter(CapturedPage.url == body.url).first()
   if not page:
       raise HTTPException(status_code=404, detail="Page not found for URL")
   ```
   FastAPI automatically formats this as:
   ```json
   {
       "detail": "Page not found for URL"
   }
   ```

2. **Global Exception Handlers (`@app.exception_handler`):**
   In HindSite, if PostgreSQL hasn't initialized the `captured_pages` table, SQLAlchemy throws `ProgrammingError`. Instead of returning an ugly 500 Internal Server Error crash trace:
   ```python
   @app.exception_handler(ProgrammingError)
   def handle_missing_table(request, exc):
       if "does not exist" in str(exc):
           return JSONResponse(
               status_code=503,
               content={"detail": "Database table not created. Run: python -m app.init_db"}
           )
       raise exc
   ```

---

### 5. Route Modularization with `APIRouter`

*Interviewer Question:* *"Your `main.py` has all endpoints in a single file. How would you refactor this for an enterprise application?"*

**The Answer:**
Use FastAPI's `APIRouter` to split routes into domain-specific modules:

```python
# app/routers/pages.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(prefix="/pages", tags=["Pages"])

@router.get("/")
def list_pages(limit: int = 50, db: Session = Depends(get_db)):
    ...
```

Then register them cleanly in `app/main.py`:
```python
# app/main.py
from app.routers import pages, search

app = FastAPI()
app.include_router(pages.router)
app.include_router(search.router)
```

---

### 6. Interactive OpenAPI Documentation

FastAPI automatically parses the Python type annotations and Pydantic models to generate interactive API documentation without writing a single line of YAML:
- **Swagger UI:** Accessible at `http://localhost:8000/docs` (interactive, execute queries directly).
- **ReDoc:** Accessible at `http://localhost:8000/redoc` (clean, presentation-focused schema reference).
- **OpenAPI Schema:** Raw JSON at `http://localhost:8000/openapi.json`.

---

## 6. Database & AI Engine Internals (PostgreSQL + pgvector + Cohere)

### 1. Connection Pooling & Engine Configuration

In `app/database.py`:
```python
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

- **Connection Pool:** Instead of opening and closing an expensive TCP socket and SSL handshake to PostgreSQL on every HTTP request, SQLAlchemy maintains a pool of persistent connections (default size 5 to 10).
- **`pool_pre_ping=True`:** Essential for production. Tests whether the connection is alive (`SELECT 1`) before handing it to a request. If PostgreSQL restarted or dropped an idle connection, it transparently reconnects instead of raising `OperationalError: SSL connection closed`.

---

### 2. pgvector & Cosine Distance (`<=>`)

In `app/services/search.py`:
```sql
SELECT id, url, title, domain, content, time_spent, scroll_percent, captured_at, thumbnail,
       1 - (embedding <=> CAST(:embedding AS vector)) as similarity
FROM captured_pages
WHERE embedding IS NOT NULL
ORDER BY embedding <=> CAST(:embedding AS vector)
LIMIT :limit
```

**Interview Explanation:**
- `embedding` is a 1024-dimension float vector (`Vector(1024)`).
- `<=>` is the **Cosine Distance** operator in pgvector.
  $$\text{Cosine Distance} = 1 - \text{Cosine Similarity}$$
- Therefore:
  $$\text{Cosine Similarity} = 1 - (\mathbf{A} \cdot \mathbf{B})$$
- By ordering by `embedding <=> query_vector` ascending, we get the closest semantic matches first.
- **pgvector Index Types (Impress the Interviewer):**
  - **IVFFlat (Inverted File Flat):** Clusters vectors into Voronoi cells. Fast build time, moderate memory usage.
  - **HNSW (Hierarchical Navigable Small World):** Multi-layer graph index. Extremely high search speed and recall, but higher memory consumption.

---

### 3. Why Two-Stage Retrieval? (Bi-Encoder vs Cross-Encoder)

*Interviewer Question:* *"Why did you use both pgvector embeddings AND Cohere Rerank? Why not just use pgvector alone?"*

| Stage | Model Type | Latency | Accuracy / Granularity |
| :--- | :--- | :--- | :--- |
| **Stage 1: pgvector (Bi-Encoder)** | Pre-computed embeddings compared via vector dot product | ~10-20 ms | High Recall, Moderate Precision. May miss subtle query subtleties. |
| **Stage 2: Cohere Rerank (Cross-Encoder)** | Passes `(query, document_text)` simultaneously into Transformer attention layers | ~150-300 ms | High Precision. Computes token-to-token cross-attention. |

**The Strategy:**
- Running a Cross-Encoder over 100,000 documents is computationally impossible in real-time.
- **Stage 1 (Bi-Encoder / pgvector):** Scans all rows in milliseconds and narrows down 100,000 pages to top 20 candidates.
- **Stage 2 (Cross-Encoder / Cohere Rerank):** Evaluates those 20 candidates in depth and delivers the top 3 ultra-relevant results to the user.

---

## 7. Minimalist Whiteboard Code Cheat-Sheet (2-Minute Code Snippets)

If an interviewer asks you to write code on a whiteboard or blank screen, use these clean, standard patterns.

### Snippet 1: Bare Minimum FastAPI App
```python
from fastapi import FastAPI

app = FastAPI(title="Demo App")

@app.get("/")
def home():
    return {"message": "Server is up"}
```

---

### Snippet 2: Pydantic Validation & Query/Path Params
```python
from fastapi import FastAPI, Path, Query
from pydantic import BaseModel, Field
from typing import Optional

class Item(BaseModel):
    name: str = Field(..., min_length=2, example="MacBook")
    price: float = Field(..., gt=0)
    in_stock: Optional[bool] = True

app = FastAPI()

@app.post("/items/{category}")
def create_item(
    category: str = Path(..., description="Item category"),
    discount: float = Query(0.0, ge=0.0, le=1.0),
    item: Item = None
):
    final_price = item.price * (1 - discount)
    return {"category": category, "name": item.name, "final_price": final_price}
```

---

### Snippet 3: Database Session Dependency Injection (`get_db`)
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://user:pass@localhost:5432/mydb"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# The Dependency Generator
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

### Snippet 4: Complete Production-Grade CRUD Endpoint
```python
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

# 1. Pydantic Schemas
class UserCreate(BaseModel):
    username: str
    email: str

class UserResponse(BaseModel):
    id: int
    username: str
    class Config:
        from_attributes = True  # Allows reading ORM objects directly

# 2. Path Operation
@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    # Check duplicate
    existing = db.query(UserModel).filter(UserModel.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Email already registered"
        )
    
    # Create and persist
    user = UserModel(username=user_in.username, email=user_in.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
```

---

## 8. Infosys SP L1 Killer Q&A (Top 15 Tricky Questions & Model Answers)

### Q1: What is the difference between FastAPI, Flask, and Django?
**Answer:**  
- **Django:** Full-stack, "batteries-included" monolith with its own ORM, admin panel, template engine, and authentication. Best for traditional CRUD sites, but heavy and historically WSGI-bound.
- **Flask:** Minimalist micro-framework. Very flexible, but natively synchronous (WSGI), lacks built-in data validation, and requires third-party plugins for OpenAPI and schemas.
- **FastAPI:** Modern asynchronous (ASGI) framework natively supporting Python type hints, automatic Pydantic validation, Dependency Injection, and native OpenAPI/Swagger generation with speeds matching NodeJS and Go.

---

### Q2: What is the role of `response_model` in `@app.get` / `@app.post`?
**Answer:**  
`response_model`:
1. **Filters Data:** Ensures that sensitive fields (like hashed passwords or internal database flags) are excluded from the output if not in the schema.
2. **Data Formatting & Validation:** Converts ORM models or dictionaries into valid JSON types.
3. **Documentation:** Generates accurate OpenAPI response schemas so API consumers know exact response structures.

---

### Q3: What happens behind the scenes when a request hits FastAPI?
**Answer:**  
1. **Socket Read:** Uvicorn receives TCP packet and parses HTTP request headers and body.
2. **ASGI Scope:** Uvicorn creates an ASGI connection `scope` dictionary and invokes FastAPI.
3. **Middleware Chain:** Request passes through middlewares (e.g., CORS headers, logging, gzip).
4. **Routing:** Starlette matches URL path and method (`POST /search`).
5. **Dependency Resolution:** FastAPI resolves dependencies (`Depends(get_db)`), executing up to `yield`.
6. **Pydantic Validation:** Body is deserialized and validated against `SearchQuery`. If invalid, returns 422 immediately.
7. **Execution:** Endpoint function executes (either on the event loop for `async def` or on a threadpool for `def`).
8. **Serialization & Cleanup:** Response is validated against `response_model`, formatted to JSON, dependency `finally:` runs (`db.close()`), and response is sent back via ASGI.

---

### Q4: How does FastAPI achieve high performance?
**Answer:**  
1. **ASGI & uvloop:** Runs on `uvloop` (Cython wrapper for `libuv`), which is 2-4x faster than standard Python `asyncio`.
2. **C-speed HTTP Parsing:** Uses `httptools` (C binding).
3. **Pydantic v2 Core:** Pydantic validation is compiled in Rust (`pydantic-core`), providing 5-15x faster validation compared to pure Python.
4. **Smart Threadpooling:** Automatically offloads synchronous functions to threadpools without locking the event loop.

---

### Q5: How do you handle long-running background tasks in FastAPI?
**Answer:**  
Using FastAPI's built-in `BackgroundTasks`:
```python
from fastapi import BackgroundTasks

def log_analytics(url: str):
    # Long running file or external write
    pass

@app.post("/capture")
def capture(page: PageCapture, bg_tasks: BackgroundTasks):
    bg_tasks.add_task(log_analytics, page.url)
    return {"status": "accepted"}
```
*Note for SP L1:* For heavy, distributed workloads (e.g., video processing or large PDF ingestion), explain that you would use **Celery or Redis Queue (RQ)** with a message broker like Redis or RabbitMQ instead of in-memory background tasks.

---

### Q6: What is the difference between Path parameters, Query parameters, and Request Body?
**Answer:**  
- **Path Parameter:** Identifies a specific resource directly in the URL path (`/pages/{page_id}`).
- **Query Parameter:** Optional key-value pairs after `?` used for sorting, filtering, or pagination (`/pages?limit=50&offset=10`).
- **Request Body:** JSON payload sent in the HTTP body, used for creating or updating resources (`POST /capture`).
FastAPI differentiates them automatically: variables declared in the route path are path parameters; scalar types not in the path are query parameters; Pydantic models are request bodies.

---

### Q7: What is the N+1 database problem and how does it relate to FastAPI and SQLAlchemy?
**Answer:**  
The N+1 problem occurs when an application executes 1 query to fetch parent records, and then executes N additional queries to fetch associated child records (e.g., fetching 50 pages, and then executing 50 separate queries to fetch tags for each page).  
**Solution:** Use eager loading in SQLAlchemy using `joinedload()` or `selectinload()` to join or fetch all children in a single optimized query.

---

### Q8: How does connection pooling work in SQLAlchemy, and why is `pool_pre_ping=True` critical?
**Answer:**  
Creating a new PostgreSQL connection takes 10-50ms (TCP handshake, SSL negotiation, authentication). A connection pool maintains pre-established connections that requests borrow and return.  
`pool_pre_ping=True` executes a lightweight `SELECT 1` heartbeat before checking out a connection. If the database was restarted or firewalled the idle socket, SQLAlchemy detects the dead connection, purges it, and creates a fresh one without throwing an error to the client.

---

### Q9: What is the purpose of `Base.metadata.create_all(bind=engine)` and how does it differ from Alembic?
**Answer:**  
- `Base.metadata.create_all` only creates tables if they **do not exist**. It never alters or adds columns to existing tables.
- In HindSite, you wrote manual `ALTER TABLE` execution in `main.py` and `init_db.py`.
- In enterprise applications, we use **Alembic** (database migration tool) to version control schema changes (add columns, alter types, create indexes) with reversible `upgrade()` and `downgrade()` scripts.

---

### Q10: How do you secure endpoints in FastAPI?
**Answer:**  
Using FastAPI's `Security` and `OAuth2PasswordBearer` utilities:
1. Inject `token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))`.
2. Decode JWT (JSON Web Token) using a secret key with `PyJWT` or `python-jose`.
3. Verify claims (`exp`, `sub`) and fetch the user.
4. Raise `HTTPException(status_code=401, detail="Invalid token")` if invalid.

---

### Q11: In HindSite, how does the Cohere embedding model work?
**Answer:**  
HindSite uses Cohere's `embed-english-v3.0`. Key architectural aspects:
- **Asymmetric Search:** Documents and queries have different semantic structures. Cohere handles this using the `input_type` parameter:
  - When saving web pages: `input_type="search_document"`.
  - When searching: `input_type="search_query"`.
- **Dimension:** Produces a dense vector of 1024 floating point numbers that encapsulate semantic meaning rather than exact keyword matches.

---

### Q12: Why did you use PostgreSQL with `pgvector` instead of Pinecone, ChromaDB, or Milvus?
**Answer:**  
1. **Single Source of Truth:** With `pgvector`, relational data (metadata, URLs, time spent, binary thumbnails) and vector embeddings live inside the same database, enabling ACID transactions and atomic updates.
2. **Filtered Search:** Allows hybrid SQL queries combining metadata filters (`WHERE domain = 'github.com' AND captured_at > NOW() - INTERVAL '7 days'`) directly with vector similarity in a single query planner pass.
3. **Infrastructure Simplicity:** No need to manage and sync an external vector database service.

---

### Q13: How does the `QueryRouter` in HindSite work?
**Answer:**  
`QueryRouter` uses regular expression intent detection:
1. Regex matches explicit navigation intent patterns (`^switch\s+to\s+`, `^go\s+to\s+`, `^open\s+`).
2. If matched, it extracts keywords and scores them against currently open browser tabs (passed in the request body from `chrome.tabs.query`).
3. If confidence exceeds `0.5`, it returns a `tab_switch` response with the `tab_id`, allowing the extension to instantly switch tabs without hitting the database or AI models.
4. Otherwise, it falls back to semantic vector search.

---

### Q14: How does FastAPI handle HTTP Status Codes?
**Answer:**  
- Default successful responses return `200 OK`.
- Can be customized on decorators: `@app.post("/users", status_code=status.HTTP_201_CREATED)`.
- Deletions typically return `204 NO_CONTENT` or `200 OK`.
- Errors are raised via `HTTPException(status_code=404, detail="...")` or handled globally via `@app.exception_handler`.

---

### Q15: How would you deploy this HindSite backend in production?
**Answer:**  
1. **Containerization:** Package application with `Dockerfile` using multi-stage build.
2. **ASGI Process Management:** Run **Gunicorn** as a process manager with **Uvicorn workers**:
   ```bash
   gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
   ```
   *(Formula for workers: `2 * (CPU Cores) + 1`)*.
3. **Reverse Proxy:** Place **Nginx** or AWS ALB in front for SSL termination, rate limiting, and static caching.
4. **Managed Database:** AWS RDS for PostgreSQL with the `pgvector` extension enabled.

---

## Final Interview Mindset Tip for Infosys SP L1
> **Do not just say what you did; say WHY you did it.**
> 
> When discussing FastAPI, mention:
> - *Why not Flask?* Because of native async ASGI performance and automatic type validation.
> - *Why `def` instead of `async def`?* Because SQLAlchemy and Cohere SDK were synchronous, so FastAPI's threadpool prevented event loop starvation.
> - *Why Two-Stage Retrieval?* Because bi-encoders give speed (100k -> 20 candidates), while cross-encoders give precision (20 -> 3 results).
>
> Answering with this level of architectural depth is what separates a Specialist Programmer (SP) from a standard systems engineer. Good luck tomorrow!

