#!/usr/bin/env python3
"""Search and upload brand logos/covers from Google Images to Directus.

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

COLLECTION = "brands"
DEFAULT_DIRECTUS_FOLDER_ID = "8114e713-88a3-47b1-b866-b0252f22455a"

PROGRESS_FILE = Path("seedBrandsImages.progress.json")
GOOGLE_PROFILE_DIR = Path(".google-profile-brands")
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
def build_query(brand_name, asset_type, suffix="", official_domain=None):
    """Prefer official logo assets or corporate media, optionally scoped to the official site."""
    name = f'"{brand_name}"'
    if asset_type == "logo":
        query = f"{name} official logo PNG transparent"
    else:
        query = f"{name} (official corporate homepage hero OR newsroom media) -logo"
    if official_domain:
        query += f" site:{official_domain}"
    return f"{query} {suffix}".strip()


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


def get_brand_media(brand_id):
    r = requests.get(
        f"{DIRECTUS_URL}/items/{COLLECTION}/{brand_id}",
        headers=HEADERS,
        params={"fields": "id,name,logo,translations.id,translations.logo,translations.cover"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]


def file_id(value):
    return value.get("id") if isinstance(value, dict) else value


def patch_brand_media(brand_id, brand, logo_id=None, cover_id=None):
    body = {}
    if logo_id and not file_id(brand.get("logo")):
        body["logo"] = logo_id

    updates = []
    for translation in brand.get("translations") or []:
        if not isinstance(translation, dict) or not translation.get("id"):
            continue
        change = {"id": translation["id"]}
        if logo_id and not file_id(translation.get("logo")):
            change["logo"] = logo_id
        if cover_id and not file_id(translation.get("cover")):
            change["cover"] = cover_id
        if len(change) > 1:
            updates.append(change)
    if updates:
        body["translations"] = {"update": updates}
    if not body:
        return False
    r = requests.patch(
        f"{DIRECTUS_URL}/items/{COLLECTION}/{brand_id}",
        headers=HEADERS,
        json=body,
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
def load_brands(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Brands file not found: {path}")
    raw = json.loads(p.read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        raw = raw.get("data", [])
    if not isinstance(raw, list):
        raise ValueError("Brands file must be a list or an object containing a data list")
    return raw


def find_image(page, brand, asset_type, args):
    name = brand.get("name") or "brand"
    website = brand.get("website") or ""
    host = urllib.parse.urlparse(website).hostname
    query = build_query(name, asset_type, args.suffix, official_domain=host)
    fallback = build_query(name, asset_type, args.suffix) if host else None

    while True:
        print(f"  Searching {asset_type}: {query}")
        try:
            urls = search_google_images(page, query)
            candidates = fetch_candidates(urls, MAX_PREVIEW if not args.auto else 1)
        except Exception as error:
            print(f"  search failed: {error}")
            candidates = []

        if not candidates and fallback and query != fallback:
            query = fallback
            fallback = None
            continue
        if not candidates:
            print(f"  no {asset_type} image found")
            return None
        if args.auto:
            return candidates[0]

        title = f"{name} {asset_type}"
        show_preview(title, candidates, tempfile.mkdtemp(prefix="seedbrand_"))
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
        default=os.path.join(os.path.dirname(__file__), "cataloge content", "brands.json"),
        help="local brands JSON export",
    )
    ap.add_argument("--suffix", default="", help="extra words added to the query")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, help="maximum brands to process")
    ap.add_argument("--auto", dest="auto", action="store_true", default=True,
                    help="upload the first valid image for each missing asset (default)")
    ap.add_argument(
        "--folder",
        default=DEFAULT_DIRECTUS_FOLDER_ID,
        help="Directus folder id for uploads (default: Brand & Store Logos)",
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
        brands = load_brands(args.file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        ap.error(str(error))
    progress = load_progress()
    print(f"Loaded {len(brands)} brands from {args.file}")

    with sync_playwright() as pw:
        ctx, page, owns_browser = open_context(pw, args)
        try:
            processed = 0
            if page.url == "about:blank":
                print("Opening Google; image searches start for brands with missing images.")
            ensure_google_session(page)
            for idx, brand in enumerate(brands):
                if idx < args.start:
                    continue
                if args.limit is not None and processed >= args.limit:
                    break
                processed += 1
                brand_id = brand.get("id") if isinstance(brand, dict) else None
                name = (brand.get("name") or "brand") if isinstance(brand, dict) else "invalid record"
                if not brand_id:
                    print(f"\n[{idx + 1}/{len(brands)}] {name}: missing Directus id; skipped")
                    continue

                print(f"\n[{idx + 1}/{len(brands)}] {name}")
                try:
                    print("  checking current Directus image fields", flush=True)
                    current = get_brand_media(brand_id)
                    translations = [
                        item for item in (current.get("translations") or [])
                        if isinstance(item, dict) and item.get("id")
                    ]
                    needs_main_logo = not file_id(current.get("logo"))
                    needs_translation_logo = any(
                        not file_id(item.get("logo")) for item in translations
                    )
                    needs_cover = any(
                        not file_id(item.get("cover")) for item in translations
                    )
                    if not translations:
                        print("  no existing translation rows; translation logo/cover cannot be attached")

                    if not needs_main_logo and not needs_translation_logo and not needs_cover:
                        print("  logo and translation images already set; skipped")
                        progress["done"][str(brand_id)] = "already complete"
                        save_progress(progress)
                        continue

                    safe_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or str(brand_id)
                    uploaded_logo = None
                    uploaded_cover = None
                    if needs_main_logo or needs_translation_logo:
                        image = find_image(page, brand, "logo", args)
                        if image:
                            uploaded_logo = upload_to_directus(
                                f"{name} logo", f"{safe_name}-logo", image["data"], image["type"], args.folder
                            )
                    if needs_cover:
                        image = find_image(page, brand, "cover", args)
                        if image:
                            uploaded_cover = upload_to_directus(
                                f"{name} cover", f"{safe_name}-cover", image["data"], image["type"], args.folder
                            )

                    changed = patch_brand_media(
                        brand_id, current, logo_id=uploaded_logo, cover_id=uploaded_cover
                    )
                    if changed:
                        print("  uploaded and linked available brand images")
                        progress["done"][str(brand_id)] = {
                            "logo": uploaded_logo,
                            "cover": uploaded_cover,
                        }
                    else:
                        print("  no image fields updated")
                        progress.setdefault("skipped", []).append(str(brand_id))
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