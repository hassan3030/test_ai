#!/usr/bin/env python3
"""
seedImagesModels.py
-------------------
Loop over models.json, search Google Images for each model using
    "<subcategory_name> <brand_name> <series_name> <name> (<year>)"
pick 1-3 images, upload them to Directus (/files) and attach them to the
`gallery` field of the item in the `models` collection.

Setup:
    pip install playwright requests
    playwright install chromium
    pip install browser-cookie3      # only needed for --import-cookies
    export DIRECTUS_TOKEN="your-token"
    export DIRECTUS_URL="https://dev-dashboard.swibba.com"

Usage:
    python seedImagesModels.py                       # reads cataloge content/models.json
    python seedImagesModels.py --file "cataloge content/models.json"
    python seedImagesModels.py --limit 10
    python seedImagesModels.py --file "cataloge content/models.json" --limit 10
    python seedImagesModels.py --channel msedge      # same, but with Edge
    python seedImagesModels.py --profile-dir "C:/Users/me/AppData/Local/Google/Chrome/User Data/Profile 1"
    python seedImagesModels.py --import-cookies chrome   # fallback: copy Google login cookies
    python seedImagesModels.py --count 2 --interactive --start 50

Browser modes
    1) --real-profile   Launches the REAL browser with your normal profile, so you are
                        already logged in to Google. Chrome/Edge must be fully closed
                        first (also check the system tray / background processes).
    2) default          Uses a separate persistent automation profile (.google-profile).
                        Log in once in that window; the login is reused on later runs.
                        Use --import-cookies only as a fallback while your browser is open.
    3) --connect-cdp    Attach to a Chrome you started yourself with
                        --remote-debugging-port=9222 (see note in --help).

At the prompt (interactive):
    1,3,5 or 1-3 -> accept those images (max --count, default 2)
    s            -> skip this model
    r            -> re-search (asks for a custom query)
    q            -> quit (progress saved, run again to resume)
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
from playwright.sync_api import sync_playwright

DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://dev-dashboard.swibba.com").rstrip("/")
DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN", "xIP-4itXBiCUGGXsxJz2zCdFsXo-Wjvo")
HEADERS = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"}

COLLECTION = "models"
GALLERY_FIELD = "gallery"

PROGRESS_FILE = Path("seedImagesModels.progress.json")
GOOGLE_PROFILE_DIR = Path(".google-profile-models")
MAX_PREVIEW = 10
MAX_IMAGES = 1
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
def build_query(m, suffix=""):
    """Build a more specific Google Images query for the exact item."""
    series = m.get("series_id") or {}
    subcategory = series.get("subcategory_id") or {}

    subcategory_name = m.get("subcategory_name") or subcategory.get("name") or ""
    series_name = m.get("series_name") or series.get("name") or ""
    model_name = m.get("name") or ""

    brand_name = m.get("brand_name")
    if not brand_name and model_name:
        brand_name = model_name.split()[0]
    if not brand_name and series_name:
        brand_name = series_name.split()[0]

    # Keep the query specific to the actual model, while avoiding repeated words.
    parts = [
        subcategory_name,
        brand_name,
        series_name,
        model_name,
        m.get("model_number") or "",
    ]

    words, seen = [], set()
    for part in parts:
        for w in str(part or "").split():
            key = w.lower().strip("()[]{}:,;.")
            if key and key not in seen:
                seen.add(key)
                words.append(w)

    text = " ".join(words)
    rd = (m.get("release_date") or "")[:4]
    if rd and rd not in seen:
        text += f" ({rd})"

    if suffix:
        return f"{text} {suffix}".strip()

    # Add a tighter visual selector to reduce generic results.
    obj_type = "car"
    if subcategory_name.lower() in {"motorcycle", "motorcycles", "bike", "bikes"}:
        obj_type = "motorcycle"
    elif subcategory_name.lower() in {"truck", "trucks"}:
        obj_type = "truck"

    return f'"{text}" {obj_type} front view'.strip()


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


def _existing_gallery(model_id):
    r = requests.get(
        f"{DIRECTUS_URL}/items/{COLLECTION}/{model_id}",
        headers=HEADERS,
        params={"fields": f"{GALLERY_FIELD}.*"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"].get(GALLERY_FIELD) or []


def add_to_gallery(model_id, file_ids, mode, junction_key):
    if mode == "m2m":
        body = {
            GALLERY_FIELD: {
                "create": [{junction_key: fid} for fid in file_ids],
                "update": [],
                "delete": [],
            }
        }
    else:  # ids
        current = _existing_gallery(model_id)
        current_ids = [g if isinstance(g, str) else g.get(junction_key) for g in current]
        body = {GALLERY_FIELD: [x for x in current_ids if x] + file_ids}

    r = requests.patch(
        f"{DIRECTUS_URL}/items/{COLLECTION}/{model_id}",
        headers=HEADERS,
        json=body,
        timeout=30,
    )
    r.raise_for_status()


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
def load_models(path):
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    if not p.exists():
        raise FileNotFoundError(f"Model file not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        raw = raw.get("data", [])
    if not isinstance(raw, list):
        raise ValueError("Model file must be a list or an object containing a data list")
    invalid = [
        index for index, model in enumerate(raw)
        if not isinstance(model, dict) or not model.get("id")
    ]
    if invalid:
        raise ValueError(
            f"Model file contains records without an id or valid object at zero-based indexes: "
            f"{invalid[:10]}"
        )
    return raw


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
        print(f"  (could not read {browser} cookies: {e}; continuing logged out)")
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
        try:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(GOOGLE_PROFILE_DIR),
                headless=args.headless,
                channel=args.channel,
                user_agent=UA,
                locale="en-US",
                args=LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
            )
        except Exception as error:
            sys.exit(
                f"Could not open the automation browser profile at {GOOGLE_PROFILE_DIR}: {error}\n"
                "That profile is likely already in use by another running copy of this script. "
                "Close the other run and retry. If you intend to use an already-running Chrome, "
                "start it with remote debugging and pass --connect-cdp <URL>. "
                "Do not delete profile lock files while Chrome may still be using the profile."
            )
        if args.import_cookies:
            cookies = load_browser_cookies(args.import_cookies)
            if cookies:
                ctx.add_cookies(cookies)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()  # reuse the blank tab
        return ctx, page, True

    # --real-profile: drive your actual profile (Chrome must be closed; may be blocked by Chrome 136+)
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
    except Exception as e:
        sys.exit(
            f"\nCould not open your browser profile: {e}\n\n"
            "Fix:\n"
            "  1. Close ALL Chrome/Edge windows (also from the system tray / Task Manager).\n"
            "  2. Run again.\n"
            "If it still fails (newer Chrome blocks automation on the default profile),\n"
            "run with:  --import-cookies chrome   (works while the browser stays open)."
        )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page, True


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--file",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "cataloge content",
            "models.json",
        ),
        help="JSON export to process (default: cataloge content/models.json)",
    )
    ap.add_argument("--suffix", default="", help="extra words added to the query")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=MAX_IMAGES, choices=[1, 2, 3],
                    help="how many images per model (1-3, default 3)")
    ap.add_argument("--auto", dest="auto", action="store_true", default=True,
                    help="upload the first working images (default)")
    ap.add_argument("--interactive", dest="auto", action="store_false",
                    help="show previews and manually choose images")
    ap.add_argument("--gallery-mode", choices=["m2m", "ids"], default="m2m")
    ap.add_argument("--junction-key", default="directus_files_id",
                    help="file key inside the M2M junction table")
    ap.add_argument("--folder", default=None, help="Directus folder id for uploads")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--channel", default="chrome", choices=["chrome", "msedge"],
                    help="which installed browser to use (default: chrome)")
    ap.add_argument("--profile-dir", type=Path, default=None,
                    help='profile folder, e.g. ".../User Data/Profile 1". Default: your "Default" profile')
    ap.add_argument("--import-cookies", metavar="BROWSER", default=None,
                    choices=["chrome", "edge", "firefox", "brave", "chromium"],
                    help="one-time fallback: copy Google cookies from this browser (browser can stay open)")
    ap.add_argument("--real-profile", action="store_true",
                    help="drive your actual Chrome profile instead of importing cookies "
                         "(Chrome must be closed; Chrome 136+ may leave a blank page)")
    ap.add_argument("--connect-cdp", metavar="URL", default=None,
                    help="attach to a running Chrome started with --remote-debugging-port=9222 "
                         "and a non-default --user-data-dir (Chrome 136+ ignores the flag on the default profile)")
    args = ap.parse_args()

    models = load_models(args.file)
    progress = load_progress()
    print(f"Loaded {len(models)} models")

    with sync_playwright() as pw:
        ctx, page, owns_browser = open_context(pw, args)

        for idx, m in enumerate(models):
            if idx < args.start:
                continue
            mid, name = m["id"], m.get("name") or "model"

            gallery = m.get(GALLERY_FIELD)
            if gallery or mid in progress["done"] or mid in progress["skipped"]:
                continue

            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or mid
            query = build_query(m, args.suffix)
            print(f"\n[{idx + 1}/{len(models)}] {name}  ->  '{query}'")

            while True:
                try:
                    urls = search_google_images(page, query)
                except Exception as e:
                    print(f"  search failed: {e}")
                    urls = []

                want = args.count if args.auto else MAX_PREVIEW
                candidates = fetch_candidates(urls, want)

                picks = []
                if not candidates:
                    print("  no images found")
                    choice = "s" if args.auto else input(
                        "  [s]kip / [r]etry with new query / [q]uit: ").strip().lower()
                elif args.auto:
                    choice = "pick"
                    picks = list(range(1, min(args.count, len(candidates)) + 1))
                else:
                    tmp = tempfile.mkdtemp(prefix="seedimg_")
                    show_preview(query, candidates, tmp)
                    choice = input(
                        f"  pick up to {args.count} (e.g. 1,3 or 1-3) / [s]kip / [r]e-search / [q]uit: "
                    ).strip().lower()

                if choice == "q":
                    save_progress(progress)
                    print("Saved. Bye.")
                    if owns_browser:
                        ctx.close()
                    return
                if choice == "s":
                    progress["skipped"].append(mid)
                    save_progress(progress)
                    break
                if choice == "r":
                    query = input("  new query: ").strip() or query
                    continue

                if choice != "pick":
                    picks = parse_selection(choice, len(candidates), args.count) or []
                if not picks:
                    print("  invalid choice")
                    continue

                file_ids = []
                for n, p in enumerate(picks, 1):
                    c = candidates[p - 1]
                    try:
                        fid = upload_to_directus(
                            f"{name} ({n})", f"{slug}-{n}", c["data"], c["type"], args.folder
                        )
                        file_ids.append(fid)
                    except requests.HTTPError as e:
                        print(f"  ✗ upload error: {e.response.status_code} {e.response.text[:300]}")

                if not file_ids:
                    print("  nothing uploaded, try again")
                    if args.auto:
                        progress["skipped"].append(mid)
                        save_progress(progress)
                        break
                    continue

                try:
                    add_to_gallery(mid, file_ids, args.gallery_mode, args.junction_key)
                    progress["done"][mid] = file_ids
                    save_progress(progress)
                    print(f"  ✓ added {len(file_ids)} image(s) to gallery")
                except requests.HTTPError as e:
                    print(f"  ✗ gallery update error: {e.response.status_code} {e.response.text[:300]}")
                    if args.auto:
                        break
                    continue
                break

            time.sleep(1.0)  # be gentle with Google

        if owns_browser:
            ctx.close()
    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved; run again to resume.")
        sys.exit(0)