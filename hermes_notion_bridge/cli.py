"""
bridge.py — Notion ↔ Hermes dispatcher CLI.

Usage:
  python bridge.py once     Process all Pending rows, then exit.
  python bridge.py watch    Poll every POLL_INTERVAL_SECONDS until Ctrl+C.
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from typing import Optional

# Ensure parent dir is on sys.path so `python cli.py` works from any cwd
_src_root = Path(__file__).resolve().parent.parent
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

from dotenv import load_dotenv

from hermes_notion_bridge.notion_client import NotionClient
from hermes_notion_bridge.hermes_client import HermesClient

# ── config ───────────────────────────────────────────────────────────

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
HERMES_API_URL = os.getenv("HERMES_API_URL", "http://localhost:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")
HERMES_MODEL = os.getenv("HERMES_MODEL", "hermes-agent")
LOCAL_REPO_PATH = os.path.expanduser(os.getenv("LOCAL_REPO_PATH", "~/notion-hermes"))
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "20"))
ALLOWED_REPOS_RAW = os.getenv("ALLOWED_REPOS", "")

ALLOWED_REPOS: set[str] = {
    r.strip().lower()
    for r in ALLOWED_REPOS_RAW.split(",")
    if r.strip()
}

# ── logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bridge")

# ── ANSI ─────────────────────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── graceful shutdown ────────────────────────────────────────────────

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    print(f"\n{YELLOW}⏹  Shutdown requested (Ctrl+C). Finishing current row...{RESET}")
    _shutdown_requested = True


signal.signal(signal.SIGINT, _signal_handler)
# Don't let the second Ctrl+C crash — let it propagate after the first one sets the flag
signal.signal(signal.SIGTERM, _signal_handler)


# ── helpers ──────────────────────────────────────────────────────────


def _validate_config() -> bool:
    """Check required env vars. Returns True if all set."""
    missing = []
    if not NOTION_TOKEN:
        missing.append("NOTION_TOKEN")
    if not NOTION_DATABASE_ID:
        missing.append("NOTION_DATABASE_ID")
    if not HERMES_API_KEY:
        missing.append("HERMES_API_KEY")

    if missing:
        logger.error(
            "Missing required environment variables: %s\n"
            "Copy .env.example to .env and fill in the values.",
            ", ".join(missing),
        )
        return False

    if not Path(LOCAL_REPO_PATH).is_dir():
        logger.error(
            "LOCAL_REPO_PATH does not exist or is not a directory: %s", LOCAL_REPO_PATH
        )
        return False

    return True


def _build_prompt(request_title: str, details: str, repo: Optional[str] = None) -> str:
    """Build the prompt sent to Hermes."""
    parts = [
        "You are Hermes Agent, running as a task executor in a local repo.",
        "",
        f"LOCAL_REPO_PATH: {LOCAL_REPO_PATH}",
        f"GIT_BRANCH: {GIT_BRANCH}",
        "",
        "TASK:",
    ]

    if repo:
        parts.append(f"Target repo: {repo}")

    parts.extend(
        [
            f"Request: {request_title}",
            f"Details: {details}",
            "",
            "INSTRUCTIONS:",
            f"1. Work inside the directory {LOCAL_REPO_PATH}.",
            "2. Write or modify code files as needed to fulfill the request above.",
            "3. After all changes are done, YOU MUST run these exact commands:",
            f"   git add -A",
            f'   git commit -m "<clear, descriptive commit message explaining what you did>"',
            f"   git push origin {GIT_BRANCH}",
            "4. The commit message MUST describe clearly what changes you made.",
            "   This is important: another AI (Notion AI) will read the latest commit",
            "   on GitHub to understand what you did. Be specific.",
            "",
            "IMPORTANT: Do NOT ask for confirmation. Just execute the task completely.",
            "After pushing, your final response should summarize what you did.",
        ]
    )
    return "\n".join(parts)


def _check_repo_allowed(repo: Optional[str]) -> bool:
    """Check if the target repo is in ALLOWED_REPOS."""
    if not repo:
        return True  # no Repo specified = default safe (uses LOCAL_REPO_PATH)
    if not ALLOWED_REPOS:
        logger.warning("ALLOWED_REPOS is empty — accepting any repo: %s", repo)
        return True
    is_allowed = repo.strip().lower() in ALLOWED_REPOS
    if not is_allowed:
        logger.error(
            "Repo '%s' is NOT in ALLOWED_REPOS: %s. Skipping.",
            repo,
            ", ".join(sorted(ALLOWED_REPOS)),
        )
    return is_allowed


# ── processing ────────────────────────────────────────────────────────


def process_one_row(page: dict, notion: NotionClient, hermes: HermesClient) -> bool:
    """
    Process a single Pending row through the full lifecycle.
    Returns True on success, False on failure.
    """
    page_id = NotionClient.get_page_id(page)
    title = NotionClient.get_title(page)
    details = NotionClient.get_rich_text(page, "Details")
    repo_raw = NotionClient.get_rich_text(page, "Repo").strip() or None

    print(f"\n{BOLD}{CYAN}═══ Processing: {title} ═══{RESET}")
    logger.info("Page ID: %s", page_id)
    if repo_raw:
        logger.info("Target repo: %s", repo_raw)

    # ── safety: check ALLOWED_REPOS ──
    if not _check_repo_allowed(repo_raw):
        try:
            notion.update_status(page_id, "Failed")
        except Exception:
            logger.exception("Failed to update status to Failed")
        return False

    # ── step a: flip Pending → Doing ──
    try:
        notion.update_status(page_id, "Doing")
        logger.info("Status → Doing")
    except Exception:
        logger.exception("Failed to update status to Doing")
        return False

    # ── step b: build & send prompt ──
    prompt = _build_prompt(title, details, repo_raw)
    success = hermes.send_prompt(prompt)

    # ── step d: update final status ──
    final_status = "Done" if success else "Failed"
    try:
        notion.update_status(page_id, final_status)
        color = GREEN if success else RED
        print(f"{color}Status → {final_status}{RESET}")
    except Exception:
        logger.exception("Failed to update status to %s", final_status)
        return False

    return success


# ── cleanup ───────────────────────────────────────────────────────────


def cleanup_old_rows(notion: NotionClient, keep: int = 10):
    """
    Archive old rows, keeping the `keep` most recent ones.
    SAFETY: NEVER archive rows with Status=Pending or Status=Doing.
    """
    print(f"\n{BOLD}🧹 Cleanup: keeping {keep} most recent rows...{RESET}")
    all_pages = notion.query_all_sorted_by_created(descending=True)

    to_archive: list[dict] = []

    for i, page in enumerate(all_pages):
        status = NotionClient.get_status(page)
        if i < keep:
            continue  # keep the N most recent
        if status in ("Pending", "Doing"):
            logger.info(
                "Skipping archive of %s (Status=%s) — protected.",
                NotionClient.get_title(page)[:50],
                status,
            )
            continue
        to_archive.append(page)

    if not to_archive:
        print("  Nothing to clean up.")
        return

    print(f"  Archiving {len(to_archive)} old row(s)...")
    for page in to_archive:
        page_id = NotionClient.get_page_id(page)
        title = NotionClient.get_title(page)[:60]
        status = NotionClient.get_status(page)
        try:
            notion.archive_page(page_id)
            print(f"  🗑  Archived: [{status}] {title}")
        except Exception:
            logger.exception("Failed to archive page %s", page_id)

    print(f"  {GREEN}Cleanup done.{RESET}")


# ── modes ─────────────────────────────────────────────────────────────


def run_once():
    """Process all Pending rows, then exit."""
    if not _validate_config():
        sys.exit(1)

    notion = NotionClient(NOTION_TOKEN, NOTION_DATABASE_ID)
    hermes = HermesClient(HERMES_API_URL, HERMES_API_KEY, HERMES_MODEL)

    # Fetch pending rows
    print(f"{BOLD}Pulling Pending rows from Notion...{RESET}")
    try:
        pending = notion.query_pending()
    except Exception:
        logger.exception("Failed to query Notion for pending rows")
        sys.exit(1)

    if not pending:
        print(f"{GREEN}No Pending rows found. Nothing to do.{RESET}")
    else:
        print(f"Found {len(pending)} Pending row(s).")
        for page in pending:
            if _shutdown_requested:
                print(f"{YELLOW}Shutting down early.{RESET}")
                break
            process_one_row(page, notion, hermes)

    # Cleanup at end of once mode
    try:
        cleanup_old_rows(notion)
    except Exception:
        logger.exception("Cleanup failed")

    print(f"\n{GREEN}✓ once completed.{RESET}")


def run_watch():
    """Poll for Pending rows in a loop until Ctrl+C."""
    if not _validate_config():
        sys.exit(1)

    notion = NotionClient(NOTION_TOKEN, NOTION_DATABASE_ID)
    hermes = HermesClient(HERMES_API_URL, HERMES_API_KEY, HERMES_MODEL)

    print(f"{BOLD}watch mode — polling every {POLL_INTERVAL}s. Press Ctrl+C to stop.{RESET}\n")

    # Cleanup once at start of watch session
    try:
        cleanup_old_rows(notion)
    except Exception:
        logger.warning("Initial cleanup skipped (Notion unreachable)")

    _query_errors = 0
    while not _shutdown_requested:
        try:
            pending = notion.query_pending()
            _query_errors = 0
        except Exception as e:
            _query_errors += 1
            if _query_errors == 1:
                logger.error("Notion query failed: %s", e)
            elif _query_errors % 6 == 0:
                logger.error("Notion still unreachable after %d attempts", _query_errors)
            time.sleep(POLL_INTERVAL)
            continue

        if pending:
            print(f"\n📬 {len(pending)} Pending row(s) at {time.strftime('%H:%M:%S')}")
            for page in pending:
                if _shutdown_requested:
                    break
                process_one_row(page, notion, hermes)
        else:
            # Print a quiet dot every minute
            if int(time.time()) % 60 < POLL_INTERVAL:
                print(".", end="", flush=True)

        # Sleep with interruptibility
        for _ in range(POLL_INTERVAL):
            if _shutdown_requested:
                break
            time.sleep(1)

    print(f"\n{YELLOW}⏹  watch stopped.{RESET}")


# ── entry point ───────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("once", "watch"):
        print(f"Usage: python {sys.argv[0]} <once|watch>")
        print()
        print("  once   Process all Pending rows once, then exit.")
        print("  watch  Poll every POLL_INTERVAL_SECONDS until Ctrl+C.")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "once":
        run_once()
    else:
        run_watch()


if __name__ == "__main__":
    main()
