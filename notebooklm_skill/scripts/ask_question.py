#!/usr/bin/env python3
"""
Simple NotebookLM Question Interface
Based on MCP server implementation - simplified without sessions

Implements hybrid auth approach:
- Persistent browser profile (user_data_dir) for fingerprint consistency
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
See: https://github.com/microsoft/playwright/issues/36139
"""

import argparse
import sys
import time
import re
import traceback
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS
from browser_utils import BrowserFactory, StealthUtils


FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)


def ask_notebooklm(question: str, notebook_url: str, headless: bool = True) -> str:
    """
    Ask a question to NotebookLM

    Args:
        question: Question to ask
        notebook_url: NotebookLM notebook URL
        headless: Run browser in headless mode

    Returns:
        Answer text from NotebookLM
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("[DIAG] state.json not found — re-authentication needed")
        return None

    print(f"[DIAG] question={question[:60]}")
    print(f"[DIAG] notebook_url={notebook_url}")

    playwright = None
    context = None

    try:
        # Start playwright
        print("[DIAG] starting playwright...")
        playwright = sync_playwright().start()
        print("[DIAG] playwright started OK")

        # Launch persistent browser context using factory
        print("[DIAG] launching browser context...")
        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )
        print("[DIAG] browser context launched OK")

        # Navigate to notebook
        page = context.new_page()
        print("[DIAG] navigating to notebook (wait_until=load)...")
        try:
            page.goto(notebook_url, wait_until="load", timeout=60000)
        except Exception as e_goto:
            # If "load" times out (JS heavy page), continue anyway — DOM is ready
            print(f"[DIAG] goto warning (non-fatal): {e_goto}")

        current_url = page.url
        try:
            page_title = page.title()
        except Exception:
            page_title = "unknown"
        print(f"[DIAG] current_url={current_url}")
        print(f"[DIAG] page_title={page_title}")

        # Verify we are on NotebookLM (not redirected to Google login)
        if "accounts.google.com" in current_url or "notebooklm.google.com" not in current_url:
            print(f"[DIAG] REDIRECT DETECTED — not on NotebookLM. URL={current_url}")
            print("[DIAG] Cookies may be invalid or Google blocked this IP. Re-auth required.")
            return None

        # Wait for query input — increased timeout for slow cloud connections
        print("[DIAG] waiting for query input selector...")
        query_element = None

        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(
                    selector,
                    timeout=60000,   # 60s — cloud is slower than local
                    state="visible"
                )
                if query_element:
                    print(f"[DIAG] found input selector: {selector}")
                    break
            except Exception:
                print(f"[DIAG] selector not found: {selector}")
                continue

        if not query_element:
            # Last resort: dump page snapshot for diagnosis
            try:
                html_snippet = page.content()[:1500]
                print(f"[DIAG] page HTML snippet: {html_snippet}")
            except Exception:
                pass
            print("[DIAG] FATAL: could not find query input — NotebookLM UI may have changed or page did not load")
            return None

        # Type question
        print("[DIAG] typing question...")
        input_selector = QUERY_INPUT_SELECTORS[0]
        StealthUtils.human_type(page, input_selector, question)

        # Submit
        print("[DIAG] submitting question...")
        page.keyboard.press("Enter")
        StealthUtils.random_delay(500, 1500)

        # Wait for response (poll for stable text)
        print("[DIAG] waiting for answer...")
        answer = None
        stable_count = 0
        last_text = None
        deadline = time.time() + 1800  # 30 minutes

        while time.time() < deadline:
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue
            except Exception:
                pass

            for selector in RESPONSE_SELECTORS:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        latest = elements[-1]
                        text = latest.inner_text().strip()
                        if text:
                            if text == last_text:
                                stable_count += 1
                                if stable_count >= 3:
                                    answer = text
                                    break
                            else:
                                stable_count = 0
                                last_text = text
                except Exception:
                    continue

            if answer:
                break

            time.sleep(1)

        if not answer:
            print("[DIAG] TIMEOUT: no answer received within deadline")
            return None

        print("[DIAG] answer received OK")
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        print(f"[DIAG] EXCEPTION: {e}")
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description='Ask NotebookLM a question')
    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser')
    args = parser.parse_args()

    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
        else:
            print(f"[DIAG] notebook '{args.notebook_id}' not found in library")
            return 1

    if not notebook_url:
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"[DIAG] using active notebook: {active['name']}")
        else:
            print("[DIAG] no notebook URL specified and no active notebook")
            return 1

    answer = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        headless=not args.show_browser
    )

    if answer:
        print("\n" + "=" * 60)
        print(f"Question: {args.question}")
        print("=" * 60)
        print()
        print(answer)
        print()
        print("=" * 60)
        return 0
    else:
        print("\n[DIAG] failed to get answer — check [DIAG] lines above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
