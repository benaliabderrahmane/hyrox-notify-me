#!/usr/bin/env python3
"""Web crawler that pings Discord when HYROX event ticket pages update."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# Events to monitor: (display_name, url)
EVENTS: List[Tuple[str, str]] = [
    ("HYROX Valencia", "https://hyroxfrance.com/fr/event/hyrox-valencia/"),
    (
        "HYROX Nice (TrainSweatEat)",
        "https://hyroxfrance.com/fr/event/trainsweateat-hyrox-nice/",
    ),
    ("HYROX Barcelona", "https://hyroxfrance.com/fr/event/hyrox-barcelona-2/"),
    # Test event: tickets already live, first run will notify.
    ("HYROX Geneva (test)", "https://hyroxfrance.com/fr/event/hyrox-geneva/"),
]

# When this term disappears from a page, the page has been updated and tickets
# are likely live. See README for the rationale.
SEARCH_TERM: str = os.getenv("SEARCH_TERM", "Ticket sales start soon!")
DISCORD_WEBHOOK_URL: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")

# State file: URLs we've already pinged about, so we don't spam on every run.
STATE_FILE: Path = Path(__file__).parent / "notified_events.json"

# Kept so daily_status_ping.py (which imports from this module) still works.
CRAWL_URL: str = os.getenv("CRAWL_URL", EVENTS[0][1])


def send_discord(content: str, webhook_url: Optional[str] = None) -> bool:
    """Post a message to a Discord webhook."""
    url = webhook_url or DISCORD_WEBHOOK_URL
    if not url:
        print("❌ DISCORD_WEBHOOK_URL not set — skipping notification.")
        return False
    try:
        response = requests.post(url, json={"content": content}, timeout=10)
        response.raise_for_status()
        print("📬 Discord message posted.")
        return True
    except Exception as e:
        print(f"❌ Discord post failed: {e}")
        return False


def load_state() -> Dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception as e:
        print(f"⚠️  Could not parse {STATE_FILE.name}: {e} — starting fresh.")
        return {}


def save_state(state: Dict[str, str]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def crawl_hyrox_website(
    url: str,
    search_term: str,
    user_key: Optional[str] = None,   # unused, kept for backward compat
    app_token: Optional[str] = None,  # unused, kept for backward compat
) -> Optional[bool]:
    """Fetch a page and check whether ``search_term`` is present.

    Returns True if the term is missing (page likely updated → tickets may be live),
    False if the term is still present, or None on error.
    """
    try:
        print(f"🔍 Crawling: {url}")
        headers: Dict[str, str] = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        page_text = BeautifulSoup(response.content, "html.parser").get_text()
        return search_term.lower() not in page_text.lower()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching {url}: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error on {url}: {e}")
        return None


def main() -> None:
    print("🏃‍♂️ HYROX Ticket Crawler")
    print("=" * 50)
    print(f"Searching for: '{SEARCH_TERM}'")
    print(f"Events monitored: {len(EVENTS)}")
    print(
        "Discord: "
        + ("Enabled" if DISCORD_WEBHOOK_URL else "Disabled (DISCORD_WEBHOOK_URL missing)")
    )
    print("=" * 50)

    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_URL not provided — exiting.")
        sys.exit(1)

    state = load_state()
    state_dirty = False
    any_live = False

    for name, url in EVENTS:
        if url in state:
            print(f"✅ {name}: already notified at {state[url]} — skipping.")
            continue

        result = crawl_hyrox_website(url, SEARCH_TERM)
        if result is True:
            any_live = True
            print(f"🎉 {name}: '{SEARCH_TERM}' missing — page updated!")
            sent = send_discord(
                f"🎉 **{name}** — page updated, tickets may be live!\n{url}"
            )
            if sent:
                state[url] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                state_dirty = True
        elif result is False:
            print(f"🚫 {name}: '{SEARCH_TERM}' still present.")
        else:
            print(f"⚠️  {name}: error during crawl.")

    if state_dirty:
        save_state(state)
        print(f"💾 State updated: {STATE_FILE.name}")

    print("\n" + "=" * 50)
    print(
        "🚨 At least one event updated — check Discord."
        if any_live
        else "😴 No changes detected."
    )


if __name__ == "__main__":
    main()
