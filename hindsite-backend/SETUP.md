# HindSite Backend – Setup Guide (Beginner-Friendly)

---

## Long-term solution: Docker with persistent data (recommended)

If your **PostgreSQL + pgvector** runs in Docker, use this so **data is never lost** when you stop the container.

### How it works

- **Docker volume** `hindsite_pgdata` stores all database files. It lives on your machine, not inside the container.
- When you **stop** the container (`docker compose stop`), the container stops but the **volume stays**. Your tables and data remain.
- When you **start** again (`docker compose up -d`), the same volume is attached. The database comes back with all data.
- An **init script** runs only the **first time** (when the volume is empty): it enables the pgvector extension and grants your app user permission to create tables. After that, the app can create `captured_pages` on startup and everything works.

### One-time setup (first time only)

1. **Open a terminal** in the backend folder:
   ```bash
   cd C:\Users\renis\Desktop\Frontend-AI-Extension\Frontend-AI-Extension\hindsite-backend
   ```

2. **Start the database** (creates the volume and runs the init script once):
   ```bash
   docker compose up -d
   ```
   Wait until the container is healthy (about 10–20 seconds).

3. **Create the table** (your `.env` already has the same user/password as in docker-compose):
   ```bash
   python -m app.init_db
   ```
   You should see: `Done: vector extension and captured_pages table are ready.`

4. **Start the backend**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

Your `.env` should use: `DATABASE_URL=postgresql://hindsite_user:hindsite123@localhost:5432/hindsite_db`. The compose file exposes port 5432.

### Every time you work on the project (daily workflow)

1. **Start the database** (if it’s not running):
   ```bash
   cd hindsite-backend
   docker compose up -d
   ```
   Data is loaded from the existing volume; nothing is re-initialized.

2. **Start the backend**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### When you’re done for the day

- **Stop the container** (data stays in the volume):
  ```bash
  docker compose stop
  ```
- Or close the terminal; the container keeps running until you stop it.

### If you ever remove the volume (data would be lost)

- `docker compose down` stops and removes the container but **keeps** the volume by default, so data is still there next time you `docker compose up -d`.
- **Only** if you run `docker compose down -v` (the `-v` removes volumes), the database would start empty again. Then you’d run `python -m app.init_db` again after the first `docker compose up -d`.

**Summary:** Use `docker compose up -d` for the DB and a **named volume** in `docker-compose.yml`. Stop with `docker compose stop` or `down` (without `-v`). Your data persists between restarts.

---

## What’s Going Wrong? (The Actual Issue)

Your backend needs a **database table** named `captured_pages` to store the web pages you capture and to run search. Here’s what’s happening:

1. **When the app starts**, it tries to create this table automatically in PostgreSQL.
2. **Creating a table** requires your database user to have **“CREATE” permission** on the database (the right to create new tables).
3. **Your current user** (`hindsite_user` in your `.env`) **does not have that permission**. So when the app tries to create the table, PostgreSQL says **“permission denied for schema public”** and the table is **never created**.
4. **When you use Search or Capture**, the app tries to read or write from `captured_pages`. Because the table doesn’t exist, you get: **“relation ‘captured_pages’ does not exist”**.

So the core issue is: **the table was never created because the database user isn’t allowed to create tables.**  
You need to create the table **once** using either:

- a user that **has** permission (e.g. the `postgres` superuser), or  
- by **giving** your `hindsite_user` the right to create tables, then running the init script.

---

## What You Need Before Starting

- **PostgreSQL** installed and running (e.g. on your PC or in Docker).
- **pgvector** extension installed in that PostgreSQL (for semantic search).
- **Python** (e.g. 3.10+) and the backend dependencies installed (`pip install -r requirements.txt`).
- A **.env** file with `DATABASE_URL` and `COHERE_API_KEY` (you already have this).

---

## Steps to Get the Backend Up and Running (In Order)

### Step 1: Make sure PostgreSQL is running

- If you use **Docker**: start the container that runs PostgreSQL (with pgvector).
- If you installed **PostgreSQL locally**: the service should be running (e.g. on port 5432).

You can check by opening a terminal and running (replace with your password if needed):

```bash
psql -U postgres -h localhost -p 5432 -c "SELECT 1"
```

If that works, PostgreSQL is reachable.

---

### Step 2: Create the database and user (if not already done)

You already have:

- Database: `hindsite_db`
- User: `hindsite_user`
- Password: `hindsite123`

If these don’t exist yet, connect as the **postgres** superuser and run:

```sql
CREATE USER hindsite_user WITH PASSWORD 'hindsite123';
CREATE DATABASE hindsite_db OWNER hindsite_user;
```

(If they already exist, skip this step.)

---

### Step 3: Install pgvector in your database (if not already)

Connect to your database as a user that can create extensions (usually `postgres`):

```bash
psql -U postgres -h localhost -p 5432 -d hindsite_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

If you get “extension vector does not exist”, you need to install the pgvector extension in PostgreSQL first (see [pgvector installation](https://github.com/pgvector/pgvector#installation)).

---

### Step 4: Create the `captured_pages` table (this fixes the “does not exist” error)

You have two options. Use **one** of them.

#### Option A – Run the init script as the `postgres` user (easiest)

This uses a user that is allowed to create tables, so the script can create the table and extension for you.

1. Open a terminal and go to the backend folder:

   ```bash
   cd C:\Users\renis\Desktop\Frontend-AI-Extension\Frontend-AI-Extension\hindsite-backend
   ```

2. Temporarily set `DATABASE_URL` to use the **postgres** user (replace `YOUR_POSTGRES_PASSWORD` with the real postgres password):

   **Windows (PowerShell):**

   ```powershell
   $env:DATABASE_URL="postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/hindsite_db"
   ```

   **Windows (Command Prompt):**

   ```cmd
   set DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/hindsite_db
   ```

3. Run the init script:

   ```bash
   python -m app.init_db
   ```

   You should see: **“Done: vector extension and captured_pages table are ready.”**

4. After that, you can **stop** overriding `DATABASE_URL` (close the terminal or open a new one). Your `.env` still has `hindsite_user` – the app will use that for normal runs. The table is already created, so the app no longer needs to create it.

#### Option B – Give `hindsite_user` permission to create tables, then run init

1. Connect as **postgres** and grant permission:

   ```bash
   psql -U postgres -h localhost -p 5432 -d hindsite_db -c "GRANT CREATE ON SCHEMA public TO hindsite_user;"
   ```

2. Go to the backend folder and run the init script **without** changing `DATABASE_URL` (so it uses `hindsite_user` from `.env`):

   ```bash
   cd C:\Users\renis\Desktop\Frontend-AI-Extension\Frontend-AI-Extension\hindsite-backend
   python -m app.init_db
   ```

   Again, you should see: **“Done: vector extension and captured_pages table are ready.”**

---

### Step 5: Confirm your .env

Your `.env` should contain:

- `DATABASE_URL=postgresql://hindsite_user:hindsite123@localhost:5432/hindsite_db`
- `COHERE_API_KEY=your_key_here`

Do **not** commit `.env` to git; it should stay local.

---

### Step 6: Start the backend server

From the **same backend folder** (`hindsite-backend`):

```bash
uvicorn app.main:app --reload --port 8000
```

You should see something like:

- `Uvicorn running on http://127.0.0.1:8000`
- No “permission denied for schema public” **table creation** error (if the table was created in Step 4, the app won’t try to create it again; if you still see it, the table wasn’t created – repeat Step 4).
- If the table is missing, you should see the ERROR log: “Table 'captured_pages' does not exist. Create it: python -m app.init_db …”

---

### Step 7: Check that the backend is up

1. **Health check**  
   Open in browser or run in another terminal:

   ```bash
   curl http://localhost:8000/health
   ```

   You should get something like: `{"status":"healthy","message":"HindSite API is running"}`.

2. **Search**  
   Use your HindSite extension and run a search, or send a POST request to `http://localhost:8000/search` with a JSON body `{"query": "test", "limit": 3, "open_tabs": []}`. You should get a 200 response (possibly with no results if you haven’t captured any pages yet), and **no** “relation ‘captured_pages’ does not exist” error.

---

## Quick Recap (Order of Steps)

1. PostgreSQL running (and pgvector installed in DB if needed).
2. Database `hindsite_db` and user `hindsite_user` exist.
3. **Create the table** by running `python -m app.init_db` (Option A with postgres user, or Option B after granting CREATE to `hindsite_user`).
4. `.env` has `DATABASE_URL` and `COHERE_API_KEY`.
5. Start server: `uvicorn app.main:app --reload --port 8000`.
6. Test: `GET /health` and then use search/capture.

Once the `captured_pages` table exists, the “relation does not exist” and “permission denied for schema public” (for creating that table) issues are resolved, and your backend is up and running.
