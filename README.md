# Hermes Notion Bridge

A lightweight CLI bridge that reads requests from a Notion database and dispatches
them to Hermes Agent for execution, then updates the status back.

Bridge **only coordinates** — it does NOT write code or run git.  
Hermes Agent does all the real work.

## Architecture

```
┌──────────┐     ┌───────────────┐     ┌─────────────────┐
│  Notion   │────▶│  bridge.py    │────▶│  Hermes Gateway  │
│  Database │◀────│  (dispatcher) │◀────│  (code + git)    │
└──────────┘     └───────────────┘     └─────────────────┘
```

You run **two terminals**:

| Terminal | Command                 | Role                        |
|----------|-------------------------|-----------------------------|
| T1       | `hermes gateway`        | API server for Hermes Agent |
| T2       | `python bridge.py …`    | Notion ↔ Hermes dispatcher  |

## Setup

```bash
cd hermes_notion_bridge
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Notion token, database ID, and Hermes config
```

### Notion setup

1. Create a Notion integration at https://www.notion.so/my-integrations
2. Copy the integration token → `NOTION_TOKEN`
3. Create a database named **"Hermes Requests"** with these properties:

| Property   | Type       | Purpose                         |
|------------|------------|---------------------------------|
| Request    | Title      | Short task title                |
| Details    | Rich text  | Full task description           |
| Status     | Select     | Pending / Doing / Done / Failed |
| Repo       | Rich text  | (optional) Target `org/repo`    |

4. Share the database with your integration (click "…" → "Add connections")
5. Copy the database ID from the URL → `NOTION_DATABASE_ID`

## Usage

### Terminal 1 — start Hermes Gateway

```bash
hermes gateway
# API server runs at http://localhost:8642
```

### Terminal 2 — run the bridge

```bash
cd /path/to/notion-hermes/hermes_notion_bridge

# Process all Pending rows once, then exit
python cli.py once

# Watch mode: poll every POLL_INTERVAL_SECONDS until Ctrl+C
python cli.py watch
```

## How it works

1. Bridge queries Notion: `Status == "Pending"`, sorted by creation time.
2. For each row:
   - Flips Status to **Doing** (prevents duplicate processing).
   - Sends the task to Hermes via streaming API.
   - Hermes writes code, commits, and pushes.
   - Bridge updates Status to **Done** (or **Failed** on error).
3. Cleanup: keeps the 10 most recent Done/Failed rows; archives older ones.
   **Never** deletes Pending or Doing rows.

## Manual smoke test

1. Open your Notion database.
2. Add a row:
   - Request: `test: add hello.txt`
   - Details: `Create a file hello.txt with the word "hello" in it`
   - Status: **Pending**
3. Run `python cli.py once`
4. Watch the terminal output — you'll see Hermes streaming its thinking and tool calls.
5. Check your local repo: a new commit should appear with `hello.txt`.
6. Notion row should be **Done**.

## Environment variables

| Variable              | Default                    | Description                       |
|-----------------------|----------------------------|-----------------------------------|
| NOTION_TOKEN          | (required)                 | Notion integration token          |
| NOTION_DATABASE_ID    | (required)                 | Database UUID                    |
| HERMES_API_URL        | `http://localhost:8642`    | Hermes Gateway API                |
| HERMES_API_KEY        | (required)                 | Hermes API key                    |
| HERMES_MODEL          | `hermes-agent`             | Model name                        |
| LOCAL_REPO_PATH       | `~/notion-hermes`          | Where code lives                  |
| GIT_BRANCH            | `main`                     | Branch to push                    |
| POLL_INTERVAL_SECONDS | `20`                       | Watch mode poll interval          |
| ALLOWED_REPOS         | (required)                 | Repo whitelist (comma-separated)  |
