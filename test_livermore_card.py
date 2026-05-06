#!/usr/bin/env python3
"""
Test Livermore Public Library card authentication via LinkedIn Learning.

Drives LinkedIn Learning's library-card login flow with Playwright and reports
whether the card is accepted, or surfaces the exact error LinkedIn returns.

Setup:
    python3 -m venv .venv && source .venv/bin/activate
    pip install playwright
    playwright install chromium

Usage:
    1. In your browser, open https://www.linkedin.com/learning, click
       "Sign in with your library card", choose "Livermore Public Library",
       and land on a URL like
         https://www.linkedin.com/learning-login/go/validate?account=103734218&authUUID=...
    2. Copy that full URL (the authUUID expires quickly).
    3. Run:
         LIVERMORE_VALIDATE_URL='<paste-url>' \
         LIBRARY_CARD_ID=<card-number> \
         LIBRARY_PIN=<pin> \
         python3 test_livermore_card.py

       Modes (env var MODE, default "both"):
         MODE=patron     only check patron login at livermore.lib.ca.us
                         (does NOT need LIVERMORE_VALIDATE_URL)
         MODE=linkedin   only check LinkedIn Learning auth
         MODE=both       patron first, then LinkedIn if patron passes

       Other optional env vars:
         HEADLESS=0    # watch the browser run
         SCREENSHOT=1  # save screenshots of final pages
"""
import os
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


SUCCESS_URL_MARKERS = ("learning-login/continue", "/learning/me", "/learning/")
FAILURE_TEXT_MARKERS = (
    "invalid",
    "incorrect",
    "not recognized",
    "could not",
    "unable to",
    "expired",
    "blocked",
    "try again",
)
PATRON_LOGIN_URL = "https://www.livermore.lib.ca.us/patroninfo"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def check_patron(card_id: str, pin: str, headless: bool, screenshot: bool) -> bool:
    """Log into Livermore's Sierra patron account. Returns True on success."""
    print(f"\n=== PATRON LOGIN CHECK ({PATRON_LOGIN_URL}) ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        page.goto(PATRON_LOGIN_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PWTimeout:
            pass

        # Sierra patron login: barcode field is usually name="code" or "name",
        # PIN is name="pin".
        barcode_loc = page.locator(
            'input[name="code"], input[name="name"], input[name="barcode"]'
        ).first
        if barcode_loc.count() == 0:
            barcode_loc = page.locator('input[type="text"]:visible').first
        barcode_loc.fill(card_id)

        pin_loc = page.locator(
            'input[name="pin"], input[type="password"]'
        ).first
        if pin_loc.count() > 0 and pin:
            pin_loc.fill(pin)

        submit = page.locator(
            'input[type="submit"], button[type="submit"]'
        ).first
        if submit.count() > 0:
            submit.click()
        else:
            (pin_loc if pin_loc.count() > 0 else barcode_loc).press("Enter")

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

        final_url = page.url
        body = page.locator("body").inner_text().strip()
        print(f"  final URL: {final_url}")

        if screenshot:
            page.screenshot(path="patron_result.png", full_page=True)
            print("  screenshot: patron_result.png")

        body_lower = body.lower()
        # Sierra success: redirected to /patroninfo/<id>/items or similar
        success = False
        if "/patroninfo/" in final_url and final_url.rstrip("/") != PATRON_LOGIN_URL.rstrip("/"):
            success = True
        if any(m in body_lower for m in ("logout", "log out", "your record", "items checked out")):
            success = True

        failure_phrases = (
            "does not match",
            "could not be matched",
            "sorry",
            "not registered",
            "barcode is invalid",
            "incorrect",
        )
        failure_hit = next((m for m in failure_phrases if m in body_lower), None)

        browser.close()

        if success and not failure_hit:
            print("RESULT (patron): SUCCESS — card + PIN accepted by library catalog.")
            return True
        if failure_hit:
            idx = body_lower.find(failure_hit)
            snippet = body[max(0, idx - 80): idx + 200].replace("\n", " ")
            print(f"RESULT (patron): FAILURE — '{failure_hit}' on page:\n  …{snippet}…")
            return False
        print("RESULT (patron): UNKNOWN — no clear success or failure markers.")
        print("--- page body (first 800 chars) ---")
        print(body[:800])
        return False


def check_linkedin(url: str, card_id: str, pin: str, headless: bool, screenshot: bool) -> int:
    """Drive the LinkedIn Learning library-card flow. Returns exit code."""
    print(f"\n=== LINKEDIN LEARNING CHECK ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        page.on("pageerror", lambda err: print(f"[pageerror] {err}"))

        print(f"→ navigating to {url[:80]}...")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        print(f"  landed on: {page.url}")

        # Locate the card-number field. LinkedIn's library-card form uses
        # different field names depending on the library's SIP2 config; try
        # the most likely selectors in order.
        card_selectors = [
            'input[name="libraryCardNumber"]',
            'input[id*="library-card"]',
            'input[id*="card"]',
            'input[name="cardNumber"]',
            'input[name="username"]',
            'input[type="text"]:visible',
        ]
        card_input = None
        for sel in card_selectors:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                card_input = loc
                print(f"  card input matched: {sel}")
                break
        if card_input is None:
            print("ERROR: could not find card-number input on the page",
                  file=sys.stderr)
            if screenshot:
                page.screenshot(path="livermore_no_input.png", full_page=True)
            return 1

        card_input.fill(card_id)

        if pin:
            pin_loc = page.locator(
                'input[type="password"], input[name="pin"], input[name="password"]'
            ).first
            if pin_loc.count() > 0:
                pin_loc.fill(pin)
                print("  PIN entered")

        # Capture LinkedIn's validation API response — that's where the real
        # outcome lives, not the page DOM (which just polls).
        api_calls: list[dict] = []

        def on_response(response):
            url = response.url
            method = response.request.method
            if method != "POST":
                return
            if not any(s in url for s in ("validate", "library", "learning-login")):
                return
            entry = {"url": url, "status": response.status}
            try:
                entry["body"] = response.text()[:2000]
            except Exception as e:
                entry["body_error"] = str(e)
            api_calls.append(entry)

        page.on("response", on_response)

        # Submit. Try a submit button, fall back to pressing Enter.
        submit = page.locator(
            'button[type="submit"], input[type="submit"], '
            'button:has-text("Continue"), button:has-text("Sign in"), '
            'button:has-text("Submit")'
        ).first
        if submit.count() > 0:
            submit.click()
        else:
            card_input.press("Enter")
        print("→ submitted form, waiting for result...")

        # Wait for the "Verifying your card" interstitial to clear, then for
        # any redirect to settle.
        try:
            page.wait_for_function(
                "() => !document.body.innerText.includes('Verifying your card')",
                timeout=45000,
            )
        except PWTimeout:
            print("  (still showing 'Verifying your card' after 45s — giving up)")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

        final_url = page.url
        body = page.locator("body").inner_text().strip()
        print(f"  final URL: {final_url}")

        if api_calls:
            print("\n--- captured validation API calls ---")
            for c in api_calls:
                print(f"  [{c['status']}] {c['url']}")
                if c.get("body"):
                    print(f"    body: {c['body']}")
                if c.get("body_error"):
                    print(f"    body_error: {c['body_error']}")

        if screenshot:
            page.screenshot(path="livermore_result.png", full_page=True)
            print("  screenshot: livermore_result.png")

        if any(m in final_url for m in SUCCESS_URL_MARKERS):
            print("\nRESULT: SUCCESS — card accepted, redirected into LinkedIn Learning.")
            return 0

        body_lower = body.lower()
        for marker in FAILURE_TEXT_MARKERS:
            idx = body_lower.find(marker)
            if idx != -1:
                snippet = body[max(0, idx - 100): idx + 250].replace("\n", " ")
                print(f"\nRESULT: FAILURE — error text on page:\n  …{snippet}…")
                return 1

        print("\nRESULT: UNKNOWN — neither success redirect nor known error text.")
        print("--- page body (first 1200 chars) ---")
        print(body[:1200])
        return 1


def main() -> int:
    card_id = os.environ.get("LIBRARY_CARD_ID")
    pin = os.environ.get("LIBRARY_PIN", "")
    url = os.environ.get("LIVERMORE_VALIDATE_URL", "")
    mode = os.environ.get("MODE", "both").lower()

    if mode not in ("both", "patron", "linkedin"):
        print(f"ERROR: MODE must be one of patron|linkedin|both (got {mode!r})",
              file=sys.stderr)
        return 2
    if not card_id:
        print("ERROR: set LIBRARY_CARD_ID env var", file=sys.stderr)
        return 2
    if mode in ("linkedin", "both") and not url:
        print("ERROR: MODE=linkedin/both requires LIVERMORE_VALIDATE_URL",
              file=sys.stderr)
        return 2

    headless = os.environ.get("HEADLESS", "1") != "0"
    screenshot = os.environ.get("SCREENSHOT", "0") == "1"

    if mode == "patron":
        return 0 if check_patron(card_id, pin, headless, screenshot) else 1

    if mode == "both":
        ok = check_patron(card_id, pin, headless, screenshot)
        if not ok:
            print("\nSkipping LinkedIn check — patron login failed, so the "
                  "card itself is the problem. Fix that at the library first.")
            return 1

    return check_linkedin(url, card_id, pin, headless, screenshot)


if __name__ == "__main__":
    sys.exit(main())
