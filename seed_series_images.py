#!/usr/bin/env python3
"""Search and upload series images from Google Images to Directus.

Uses a persistent browser profile and reuses its Google login on later runs. On the first
run, sign in once if prompted. Google may still occasionally show a CAPTCHA. Requires
Playwright and DIRECTUS_TOKEN; no OpenAI key needed.
"""

import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import tempfile
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8-sig") as stream:
            for line in stream:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value

DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://dev-dashboard.swibba.com").rstrip("/")
DIRECTUS_TOKEN = (os.getenv("DIRECTUS_TOKEN") or "").replace("Bearer ", "").strip()
HEADERS = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"}

COLLECTION = "series"
DEFAULT_DIRECTUS_FOLDER_ID = "e05b30a2-10b4-454f-a5ec-045b5dfd7c5a"

PROGRESS_FILE = Path("seedSeriesImages.progress.json")
GOOGLE_PROFILE_DIR = Path(".google-profile-series-images")
MAX_PREVIEW = 10
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

IMG_RE = re.compile(
    r'\["(https?://[^"\\]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\\]*)?)",\s*\d+,\s*\d+\]',
    re.IGNORECASE,
)
BAD_HOSTS = ("gstatic.com", "google.com", "googleusercontent.com", "ggpht.com")


# --------------------------------------------------------------------------- #
# Query building
# --------------------------------------------------------------------------- #
def build_query(series_name, suffix=""):
    """Search for an official product image of a series."""
    return f'"{series_name}" product image {suffix}'.strip()


# --------------------------------------------------------------------------- #
# Google Images scraping
# --------------------------------------------------------------------------- #
def dismiss_consent(page):
    for label in ("Reject all", "Accept all", "I agree", "رفض الكل", "قبول الكل"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click(timeout=2000)
                page.wait_for_load_state("domcontentloaded")
                return
        except Exception:
            pass


def search_google_images(page, query, pool=40):
    """Return a list of full-size image URLs (up to `pool`)."""
    url = "https://www.google.com/search?" + urllib.parse.urlencode(
        {"q": query, "tbm": "isch", "hl": "en"}
    )
    page.goto(url, wait_until="domcontentloaded")
    dismiss_consent(page)

    if "/sorry/" in page.url or "captcha" in page.url.lower():
        input("Google shows a captcha. Solve it in the browser, then press Enter...")

    page.wait_for_timeout(1500)
    page.mouse.wheel(0, 2500)
    page.wait_for_timeout(1200)

    content = page.content()
    content = (
        content.replace("\\u003d", "=")
        .replace("\\u0026", "&")
        .replace("\\/", "/")
    )

    urls, seen = [], set()
    for m in IMG_RE.finditer(content):
        u = html.unescape(m.group(1))
        host = urllib.parse.urlparse(u).netloc.lower()
        if any(host.endswith(b) for b in BAD_HOSTS):
            continue
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= pool:
            break
    return urls


# --------------------------------------------------------------------------- #
# Download + preview
# --------------------------------------------------------------------------- #
def download_image(url, timeout=20):
    """Return (bytes, content_type) or None."""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA, "Referer": "https://www.google.com/"},
            timeout=timeout,
        )
        ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if r.status_code == 200 and ctype.startswith("image/") and len(r.content) > 2000:
            return r.content, ctype
    except requests.RequestException:
        pass
    return None


def fetch_candidates(urls, want):
    """Download until we have `want` valid, non-duplicate images."""
    out, hashes = [], set()
    for u in urls:
        got = download_image(u)
        if not got:
            continue
        h = hashlib.md5(got[0]).hexdigest()
        if h in hashes:
            continue
        hashes.add(h)
        out.append({"url": u, "data": got[0], "type": got[1]})
        if len(out) >= want:
            break
    return out


def show_preview(title, candidates, tmpdir):
    cards = []
    for i, c in enumerate(candidates, 1):
        ext = mimetypes.guess_extension(c["type"]) or ".jpg"
        p = Path(tmpdir) / f"{i}{ext}"
        p.write_bytes(c["data"])
        cards.append(
            f'<div class="c"><div class="n">{i}</div><img src="{p.name}"></div>'
        )
    page = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui;background:#111;color:#eee;margin:20px}}
.g{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}
.c{{position:relative;background:#222;border-radius:8px;overflow:hidden;height:220px}}
.c img{{width:100%;height:100%;object-fit:contain}}
.n{{position:absolute;top:6px;left:6px;background:#e11;color:#fff;font-weight:700;
    padding:2px 9px;border-radius:12px;z-index:2}}
</style><h2>{html.escape(title)}</h2><div class="g">{''.join(cards)}</div>"""
    index = Path(tmpdir) / "index.html"
    index.write_text(page, encoding="utf-8")
    webbrowser.open(index.as_uri())


def parse_selection(text, n, max_pick):
    """'1,3,5' or '1-3' -> [1,3,5]; returns None if invalid."""
    picks = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        if re.fullmatch(r"\d+-\d+", part):
            a, b = map(int, part.split("-"))
            picks.extend(range(a, b + 1))
        elif part.isdigit():
            picks.append(int(part))
        else:
            return None
    picks = list(dict.fromkeys(picks))  # dedupe, keep order
    if not picks or any(p < 1 or p > n for p in picks):
        return None
    return picks[:max_pick]


# --------------------------------------------------------------------------- #
# Directus
# --------------------------------------------------------------------------- #
def upload_to_directus(title, slug, data, ctype, folder=None):
    if folder is None:
        folder = DEFAULT_DIRECTUS_FOLDER_ID
    ext = mimetypes.guess_extension(ctype) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    files = {"file": (f"{slug}{ext}", data, ctype)}
    form = {"title": title}
    if folder:
        form["folder"] = folder
    r = requests.post(
        f"{DIRECTUS_URL}/files", headers=HEADERS, files=files, data=form, timeout=60
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def get_series(series_id):
    r = requests.get(
        f"{DIRECTUS_URL}/items/{COLLECTION}/{series_id}",
        headers=HEADERS,
        params={"fields": "id,name,image"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]


def file_id(value):
    return value.get("id") if isinstance(value, dict) else value


def patch_series_image(series_id, current_image, image_id):
    if file_id(current_image):
        return False
    r = requests.patch(
        f"{DIRECTUS_URL}/items/{COLLECTION}/{series_id}",
        headers=HEADERS,
        json={"image": image_id},
        timeout=30,
    )
    r.raise_for_status()
    return True


# --------------------------------------------------------------------------- #
# Progress
# --------------------------------------------------------------------------- #
def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": {}, "skipped": []}


def save_progress(p):
    PROGRESS_FILE.write_text(json.dumps(p, indent=2))


# --------------------------------------------------------------------------- #
# Browser / profile helpers
# --------------------------------------------------------------------------- #
def load_series(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Series file not found: {path}")
    raw = json.loads(p.read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        raw = raw.get("data", [])
    if not isinstance(raw, list):
        raise ValueError("Series file must be a list or an object containing a data list")
    return raw


def find_image(page, series, args):
    name = series.get("name") or "series"
    query = build_query(name, args.suffix)

    while True:
        print(f"  Searching image: {query}")
        try:
            urls = search_google_images(page, query)
            candidates = fetch_candidates(urls, MAX_PREVIEW if not args.auto else 1)
        except Exception as error:
            print(f"  search failed: {error}")
            candidates = []

        if not candidates:
            print("  no series image found")
            return None
        if args.auto:
            return candidates[0]

        title = f"{name} product image"
        show_preview(title, candidates, tempfile.mkdtemp(prefix="seedseries_"))
        choice = input("  select image number / [r]e-search / [s]kip / [q]uit: ").strip().lower()
        if choice == "q":
            raise KeyboardInterrupt
        if choice == "s":
            return None
        if choice == "r":
            query = input("  new query: ").strip() or query
            fallback = None
            continue
        picks = parse_selection(choice, len(candidates), 1)
        if picks:
            return candidates[picks[0] - 1]
        print("  invalid choice")


def default_profile_dir(channel):
    """Your regular, logged-in browser profile folder ('Default')."""
    home = Path.home()
    edge = channel.startswith("msedge")
    if sys.platform.startswith("win"):
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        base = local / ("Microsoft/Edge" if edge else "Google/Chrome") / "User Data"
    elif sys.platform == "darwin":
        base = home / "Library/Application Support" / ("Microsoft Edge" if edge else "Google/Chrome")
    else:
        base = home / ".config" / ("microsoft-edge" if edge else "google-chrome")
    return base / "Default"


def resolve_browser_profile(profile_dir: Path):
    """
    Split a profile folder into (user_data_dir, chrome_args).

    Chrome needs the PARENT folder as --user-data-dir and the profile name via
    --profile-directory. Passing ".../User Data/Default" directly as user-data-dir
    silently creates a brand-new nested profile (= a different, logged-out session).
    """
    if profile_dir.name == "Default" or profile_dir.name.startswith("Profile "):
        return profile_dir.parent, [f"--profile-directory={profile_dir.name}"]
    return profile_dir, []


def load_browser_cookies(browser):
    """Read Google cookies from the user's real browser -> Playwright cookie dicts."""
    try:
        import browser_cookie3
    except ImportError:
        print("  (pip install browser-cookie3 to reuse your Google login; continuing logged out)")
        return []
    getter = getattr(browser_cookie3, browser, None)
    if getter is None:
        print(f"  (unsupported browser for cookies: {browser}; continuing logged out)")
        return []
    try:
        jar = getter(domain_name="google.com")
    except Exception as e:
        print(f"  (could not import {browser} cookies: {e})")
        print("  (sign in to Google in the automation browser once; that profile is reused on later runs)")
        return []

    cookies = []
    for c in jar:
        if not c.value:
            continue
        item = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path or "/",
            "secure": bool(c.secure),
            "httpOnly": bool(c.has_nonstandard_attr("HttpOnly")),
        }
        if c.expires:
            item["expires"] = float(c.expires)
        cookies.append(item)
    print(f"Imported {len(cookies)} Google cookies from {browser}")
    return cookies


LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


def open_context(pw, args):
    """Return (ctx, page, owns_browser)."""
    if args.connect_cdp:
        print(f"Connecting to active browser: {args.connect_cdp}")
        connected = pw.chromium.connect_over_cdp(args.connect_cdp)
        ctx = connected.contexts[0] if connected.contexts else connected.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return ctx, page, False

    if not args.real_profile:
        return launch_automation_context(pw, args, args.import_cookies)

    # Drive the actual browser profile (the browser must be closed).
    profile = args.profile_dir or default_profile_dir(args.channel)
    user_data_dir, extra = resolve_browser_profile(Path(profile))
    print(f"Opening your {args.channel} profile: {profile}")
    try:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=args.headless,
            channel=args.channel,
            locale="en-US",
            args=extra + LAUNCH_ARGS,
            ignore_default_args=["--enable-automation"],
        )
    except Exception as error:
        print(f"Could not open the signed-in browser profile: {error}")
        print("Falling back to the persistent automation profile and importing browser cookies.")
        cookie_browser = args.import_cookies or ("edge" if args.channel == "msedge" else "chrome")
        return launch_automation_context(pw, args, cookie_browser)
    if args.import_cookies:
        cookies = load_browser_cookies(args.import_cookies)
        if cookies:
            ctx.add_cookies(cookies)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page, True


def launch_automation_context(pw, args, cookie_browser=None):
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(GOOGLE_PROFILE_DIR),
        headless=args.headless,
        channel=args.channel,
        user_agent=UA,
        locale="en-US",
        args=LAUNCH_ARGS,
        ignore_default_args=["--enable-automation"],
    )
    if cookie_browser:
        cookies = load_browser_cookies(cookie_browser)
        if cookies:
            ctx.add_cookies(cookies)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page, True


def is_google_login_url(url):
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname == "accounts.google.com" or "servicelogin" in parsed.path.lower()


def ensure_google_session(page):
    if page.url == "about:blank" or not page.url.startswith("https://www.google."):
        try:
            page.goto("https://www.google.com", wait_until="domcontentloaded")
        except PlaywrightError:
            if not is_google_login_url(page.url):
                raise

    while is_google_login_url(page.url) or page.locator('a[href*="ServiceLogin"]').count():
        print("Sign in to Google in this browser profile once; the session will be reused.")
        input("Complete sign-in in the browser, then press Enter to continue...")
        try:
            page.wait_for_function(
                "location.hostname !== 'accounts.google.com'", timeout=120000
            )
        except PlaywrightTimeoutError:
            print("Google still shows sign-in; finish any remaining verification in the browser.")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--file",
        default=os.path.join(os.path.dirname(__file__), "cataloge content", "series.json"),
        help="local series JSON export",
    )
    ap.add_argument("--suffix", default="", help="extra words added to the query")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, help="maximum series to process")
    mode_group = ap.add_mutually_exclusive_group()
    mode_group.add_argument("--auto", dest="auto", action="store_true",
                            help="upload the first valid Google Images result (default)")
    mode_group.add_argument("--interactive", dest="auto", action="store_false",
                            help="review an image preview before uploading")
    ap.set_defaults(auto=True)
    ap.add_argument(
        "--folder",
        default=DEFAULT_DIRECTUS_FOLDER_ID,
        help="Directus folder id for uploads (default: Category & Subcategory Images)",
    )
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--channel", default="chrome", choices=["chrome", "msedge"],
                    help="which installed browser to use (default: chrome)")
    ap.add_argument("--profile-dir", type=Path, default=None,
                    help='profile folder, e.g. ".../User Data/Profile 1". Default: your "Default" profile')
    ap.add_argument("--import-cookies", metavar="BROWSER", default=None,
                    choices=["chrome", "edge", "firefox", "brave", "chromium"],
                    help="one-time fallback: copy Google cookies from this browser (browser can stay open)")
    profile_group = ap.add_mutually_exclusive_group()
    profile_group.add_argument("--real-profile", dest="real_profile", action="store_true",
                               help="use your signed-in browser profile (Chrome must be closed)")
    profile_group.add_argument("--automation-profile", dest="real_profile", action="store_false",
                               help="use the persistent automation profile (default)")
    ap.set_defaults(real_profile=False)
    ap.add_argument("--connect-cdp", metavar="URL", default=None,
                    help="attach to a running Chrome started with --remote-debugging-port=9222 "
                         "and a non-default --user-data-dir (Chrome 136+ ignores the flag on the default profile)")
    args = ap.parse_args()

    if not DIRECTUS_TOKEN:
        ap.error("Set DIRECTUS_TOKEN in the environment or .env file")
    try:
        series_list = load_series(args.file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        ap.error(str(error))
    progress = load_progress()
    print(f"Loaded {len(series_list)} series from {args.file}")

    with sync_playwright() as pw:
        ctx, page, owns_browser = open_context(pw, args)
        try:
            processed = 0
            if page.url == "about:blank":
                print("Opening Google; image searches start for series with missing images.")
            ensure_google_session(page)
            for idx, series in enumerate(series_list):
                if idx < args.start:
                    continue
                if args.limit is not None and processed >= args.limit:
                    break
                processed += 1
                series_id = series.get("id") if isinstance(series, dict) else None
                name = (series.get("name") or "series") if isinstance(series, dict) else "invalid record"
                if not series_id:
                    print(f"\n[{idx + 1}/{len(series_list)}] {name}: missing Directus id; skipped")
                    continue

                print(f"\n[{idx + 1}/{len(series_list)}] {name}")
                if series.get("image") or str(series_id) in progress["done"]:
                    print("  image already present or already processed; skipped")
                    continue
                try:
                    print("  checking current Directus image", flush=True)
                    current = get_series(series_id)
                    if file_id(current.get("image")):
                        print("  image already set in Directus; skipped")
                        progress["done"][str(series_id)] = "already complete"
                        save_progress(progress)
                        continue

                    image = find_image(page, series, args)
                    if not image:
                        progress.setdefault("skipped", []).append(str(series_id))
                        save_progress(progress)
                        continue

                    safe_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or str(series_id)
                    image_id = upload_to_directus(
                        name, safe_name, image["data"], image["type"], args.folder
                    )
                    patch_series_image(series_id, current.get("image"), image_id)
                    print(f"  uploaded and linked image {image_id}")
                    progress["done"][str(series_id)] = image_id
                    save_progress(progress)
                except requests.RequestException as error:
                    detail = getattr(getattr(error, "response", None), "text", "")
                    print(f"  Directus/image request failed: {error} {detail[:300]}")
                except Exception as error:
                    print(f"  failed: {error}")
                time.sleep(1.0)
        except KeyboardInterrupt:
            save_progress(progress)
            print("\nInterrupted. Progress saved; run again to resume.")
        finally:
            if owns_browser:
                try:
                    ctx.close()
                except Exception:
                    pass
    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved; run again to resume.")
        sys.exit(0)