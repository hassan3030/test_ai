#!/usr/bin/env python3
"""Fill missing series images in Directus with images found by AI + web sources.

For every series in the JSON export that has no image:
  1. Collect candidate image links from:
       - Wikidata / Wikimedia Commons (main image of the series)     -> reliable
       - Wikipedia lead image of the best-matching article            -> reliable
       - OpenAI web search (returns pages/links it actually saw; pages are scraped for images)
  2. Every link is downloaded and verified server-side (real image bytes, not HTML / 404).
  3. A local review UI (http://127.0.0.1:8765) shows ALL valid candidates BEFORE upload.
     Click the one you want, then Approve. Or paste a URL / ask the AI again with a hint.
  4. The approved image is uploaded to Directus and linked to the series.

No Playwright / Google login needed.

Requires:  pip install requests
Env (.env supported):  DIRECTUS_TOKEN, OPENAI_API_KEY (not needed with --no-ai)
Optional env:          DIRECTUS_URL, OPENAI_MODEL (default gpt-4.1-mini)
"""

import argparse
import base64
import hashlib
import html as htmllib
import json
import mimetypes
import os
import queue
import re
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

# --------------------------------------------------------------------------- #
# Env
# --------------------------------------------------------------------------- #
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
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

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

COLLECTION = "series"
ASSET = "image"
VERIFY = True        # ask a vision model whether each candidate really shows the series
MIN_SCORE = 6        # 0-10 relevance needed to be shown
BRAND_NAMES = {}     # brand id -> brand name (from brands.json)
PROGRESS_FILE = Path("seedSeriesImages.progress.json")
MAX_CANDIDATES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_BYTES = 300
MIN_PAGE_IMAGE_BYTES = 15000  # filters icons/trackers when scraping pages
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Wikimedia blocks generic/spoofed browser agents; it wants a descriptive one.
WIKI_UA = "SwibbaSeriesSeeder/1.0 (https://swibba.com; series image seeding) python-requests"
WIKI_HOSTS = ("wikimedia.org", "wikipedia.org", "wikidata.org")


def is_wiki(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in WIKI_HOSTS)


# --------------------------------------------------------------------------- #
# Series naming / context
# --------------------------------------------------------------------------- #
def brand_context(series):
    """Brand name for the series: from the record itself, or looked up by id in brands.json."""
    for key in ("brand", "brand_id", "brand_name"):
        b = series.get(key)
        if isinstance(b, dict):
            tr = b.get("translations") or [{}]
            b = b.get("name") or (tr[0].get("name") if isinstance(tr[0], dict) else None) or b.get("id")
        if b in (None, ""):
            continue
        b = str(b).strip()
        if b in BRAND_NAMES:
            return BRAND_NAMES[b]
        if not re.fullmatch(r"[0-9a-fA-F-]{8,}|\d+", b):
            return b
    return ""


def norm(text):
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", (text or "").lower()).strip()


def search_name(series):
    name = (series.get("name") or "").strip()
    brand = brand_context(series)
    if brand and brand.lower() not in name.lower():
        return f"{brand} {name}"
    return name


# --------------------------------------------------------------------------- #
# Fetching + validating images
# --------------------------------------------------------------------------- #
def sniff_image(data):
    """Detect the real image type from bytes (servers often send wrong Content-Type)."""
    head = data[:16]
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if b"<svg" in data[:4000].lower():
        return "image/svg+xml"
    return None


def fetch(url, timeout=20):
    """Return ('image', data, ctype) | ('html', text, final_url) | ('fail', reason)."""
    parsed = urllib.parse.urlparse(url)
    headers = {
        "User-Agent": WIKI_UA if is_wiki(url) else UA,
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*,text/html;q=0.8,*/*;q=0.5",
    }
    if not is_wiki(url):
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except requests.RequestException as error:
        return ("fail", f"{type(error).__name__}")
    if r.status_code != 200:
        return ("fail", f"HTTP {r.status_code}")
    data = r.content
    if len(data) > MAX_IMAGE_BYTES:
        return ("fail", "file too large")
    mime = sniff_image(data)
    if mime:
        if len(data) < MIN_IMAGE_BYTES:
            return ("fail", "image too small")
        return ("image", data, mime)
    ctype = r.headers.get("Content-Type", "").lower()
    if "html" in ctype or data[:300].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return ("html", r.text[:1_500_000], r.url)
    return ("fail", f"not an image ({ctype.split(';')[0] or 'unknown type'})")


def normalize_url(url):
    """Drop tracking params; turn Wikipedia/Commons 'File:' pages into a direct file URL."""
    url = url.strip().rstrip(".,;)")
    p = urllib.parse.urlparse(url)
    if p.query:
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith("utm_")]
        url = urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q)))
    m = re.search(r"/wiki/(?:File|Image):(.+?)(?:[?#].*)?$", url)
    if m and is_wiki(url):
        return commons_file_url(urllib.parse.unquote(m.group(1)))
    return url


def commons_file_url(filename):
    name = urllib.parse.quote(filename.replace(" ", "_"))
    suffix = "?width=1200" if filename.lower().endswith(".svg") else ""  # SVG -> PNG render
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{name}{suffix}"


# --------------------------------------------------------------------------- #
# Sources 1+2: Wikidata (P18 image) and Wikipedia lead image
# --------------------------------------------------------------------------- #
BAD_DESC = ("television", "tv series", "web series", "film", "novel", "album", "manga", "anime",
            "episode", "video game", "book", "song", "comic", "band")


def wikidata_images(series):
    """Only entities whose label contains the series name (and brand), and are not TV/film/etc."""
    name, brand = norm(series.get("name")), norm(brand_context(series))
    ids = []
    for lang in ("en", "ar"):
        r = requests.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbsearchentities", "search": search_name(series), "language": lang,
                    "format": "json", "limit": 8, "type": "item"},
            headers={"User-Agent": WIKI_UA}, timeout=20,
        )
        for x in r.json().get("search", []):
            label, desc = norm(x.get("label")), (x.get("description") or "").lower()
            if name not in label:
                continue
            if brand and brand not in label and brand not in norm(desc):
                continue
            if any(w in desc for w in BAD_DESC):
                continue
            ids.append(x["id"])
        if ids:
            break
    ids = ids[:3]
    if not ids:
        return []
    r = requests.get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbgetentities", "ids": "|".join(ids), "props": "claims", "format": "json"},
        headers={"User-Agent": WIKI_UA}, timeout=20,
    )
    entities = r.json().get("entities", {})
    urls = []
    for qid in ids:
        for claim in (entities.get(qid, {}).get("claims", {}).get("P18") or [])[:2]:
            try:
                urls.append(commons_file_url(claim["mainsnak"]["datavalue"]["value"]))
            except (KeyError, TypeError):
                pass
    return urls


def wikipedia_images(series):
    """Lead images only of articles whose TITLE matches the series name (no loose full-text hits)."""
    name, brand = norm(series.get("name")), norm(brand_context(series))
    r = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "generator": "search", "gsrsearch": search_name(series), "gsrlimit": 5,
                "prop": "pageimages", "piprop": "original", "format": "json"},
        headers={"User-Agent": WIKI_UA}, timeout=20,
    )
    pages = (r.json().get("query") or {}).get("pages", {}).values()
    best, other = [], []
    for page in sorted(pages, key=lambda p: p.get("index", 99)):
        title, src = norm(page.get("title")), (page.get("original") or {}).get("source")
        if not src or name not in title:
            continue
        (best if (not brand or brand in title) else other).append(src)
    return best or other


# --------------------------------------------------------------------------- #
# Source 3: OpenAI web search -> links it actually saw
# --------------------------------------------------------------------------- #
def build_prompt(series, hint="", bad_urls=()):
    name = series.get("name") or "series"
    brand = brand_context(series)
    parts = [
        "Use web search to find ONE good product image of this series: a clear, official-looking "
        "photo of the product/series (clean background preferred, no text overlays, no watermarks, "
        "no collages, at least 600px).",
        f"Series name: {name}",
    ]
    if brand:
        parts.append(f"Brand: {brand}")
    parts += [
        "",
        "Rules:",
        "- Return up to 8 URLs you ACTUALLY saw while searching. Never guess or construct a URL.",
        "- The image must show EXACTLY this series (not another model, not the brand logo, not a banner).",
        "- Direct image-file URLs are best. If you did not see a direct image URL, return the exact page URL "
        "(official site, press/media kit, Wikipedia or Wikimedia Commons page) where the image appears; "
        "the program will extract the image from that page.",
        '- Reply with ONLY JSON: {"urls": ["https://...", "https://..."]}   (or {"urls": []})',
    ]
    if hint:
        parts += ["", f"Extra instruction from the user: {hint}"]
    if bad_urls:
        parts += ["", "Already tried, do NOT return again:"] + [f"- {u}" for u in list(bad_urls)[-20:]]
    return "\n".join(parts)


def ask_ai_for_urls(series, hint="", bad_urls=()):
    body = {
        "model": OPENAI_MODEL,
        "tools": [{"type": "web_search"}],
        "input": build_prompt(series, hint, bad_urls),
        "max_output_tokens": 1500,
    }
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "content-type": "application/json"},
        json=body, timeout=120,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI API {r.status_code}: {r.text[:300]}")
    response = r.json()
    text, cited, parts = response.get("output_text", ""), [], []
    for output in response.get("output", []):
        if output.get("type") != "message":
            continue
        for item in output.get("content", []):
            if item.get("type") == "output_text":
                parts.append(item.get("text", ""))
                for ann in item.get("annotations", []):
                    if ann.get("type") == "url_citation" and ann.get("url"):
                        cited.append(ann["url"])
    text = (text or "".join(parts)).strip()

    urls = []
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        payload = json.loads(match.group(0) if match else text)
        urls = payload.get("urls") or [] if isinstance(payload, dict) else []
    except json.JSONDecodeError:
        urls = re.findall(r'https?://[^\s"\'<>]+', text)
    # URLs the model really visited (citations) are the most trustworthy -> add them too
    out, seen = [], set(bad_urls)
    for u in list(urls) + cited:
        if not isinstance(u, str) or not u.startswith(("http://", "https://")):
            continue
        u = normalize_url(u)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:12]


# --------------------------------------------------------------------------- #
# Scrape images out of an HTML page (AI-returned pages)
# --------------------------------------------------------------------------- #
def _attr(tag, name):
    m = re.search(rf'\b{name}\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def extract_image_urls(page, base):
    og = []
    for tag in re.findall(r"<meta\b[^>]*>", page, re.IGNORECASE):
        key = (_attr(tag, "property") or _attr(tag, "name")).lower()
        if key in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            if _attr(tag, "content"):
                og.append(_attr(tag, "content"))
    imgs = []
    for tag in re.findall(r"<img\b[^>]*>", page, re.IGNORECASE):
        src = _attr(tag, "data-src") or _attr(tag, "src")
        if not src or src.startswith("data:"):
            continue
        meta = " ".join([src, _attr(tag, "alt"), _attr(tag, "class"), _attr(tag, "id")]).lower()
        if not re.search(r"logo|icon|sprite|avatar|pixel|tracking|spinner|\.gif", meta):
            imgs.append(src)
    out, seen = [], set()
    for u in og[:2] + imgs[:4]:
        full = urllib.parse.urljoin(base, u)
        if full.startswith(("http://", "https://")) and full not in seen:
            seen.add(full)
            out.append(full)
    return out


def resolve_images(url, source, log):
    """A link may be an image or a page. Return a list of validated image dicts."""
    res = fetch(url)
    if res[0] == "image":
        return [{"url": url, "data": res[1], "type": res[2], "source": source}]
    if res[0] == "fail":
        log(f"x {res[1]}: {url[:95]}")
        return []
    found = []
    for img_url in extract_image_urls(res[1], res[2])[:6]:
        got = fetch(img_url)
        if got[0] == "image" and len(got[1]) >= MIN_PAGE_IMAGE_BYTES:
            found.append({"url": img_url, "data": got[1], "type": got[2], "source": f"{source} page"})
        elif got[0] == "fail":
            log(f"x {got[1]}: {img_url[:95]}")
    if not found:
        log(f"no usable image on page: {url[:95]}")
    return found


def verify_image(series, img):
    """Ask a vision model if the image really shows this series. Returns (score 0-10, reason) or None."""
    if img["type"] == "image/svg+xml" or len(img["data"]) > 8 * 1024 * 1024:
        return None
    prompt = (
        f"Does this image clearly show the product series \"{search_name(series)}\"?\n"
        "Score 0-10: 10 = clearly a photo of exactly this product/series; 5 = same brand but a different "
        "product; 0 = unrelated (logo only, banner, person, building, different product, tv show art).\n"
        'Be strict. Reply ONLY with JSON: {"score": <int>, "reason": "<max 8 words>"}'
    )
    data_url = f"data:{img['type']};base64,{base64.b64encode(img['data']).decode()}"
    body = {
        "model": OPENAI_MODEL,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": data_url, "detail": "low"}]}],
        "max_output_tokens": 120,
    }
    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "content-type": "application/json"},
            json=body, timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
        resp = r.json()
        text = resp.get("output_text") or "".join(
            i.get("text", "") for o in resp.get("output", []) if o.get("type") == "message"
            for i in o.get("content", []) if i.get("type") == "output_text")
        data = json.loads(re.search(r"\{.*\}", text, re.DOTALL).group(0))
        return max(0, min(10, int(data["score"]))), str(data.get("reason", ""))[:80]
    except Exception as error:
        log(f"verify failed: {error}")
        return None


def rank_candidates(series, cands, log):
    """Score every candidate for relevance, drop the unrelated ones, best first."""
    if not (VERIFY and OPENAI_API_KEY and cands):
        return cands[:MAX_CANDIDATES]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: verify_image(series, c), cands))
    for c, res in zip(cands, results):
        c["score"], c["reason"] = res if res else (None, "not verified")
    good = [c for c in cands if c["score"] is None or c["score"] >= MIN_SCORE]
    for c in cands:
        if c not in good:
            log(f"dropped (score {c['score']}/10, {c['reason']}): {c['url'][:80]}")
    if not good:  # keep the 3 best so you can still choose manually (they are clearly labelled)
        good = sorted(cands, key=lambda c: -(c["score"] or 0))[:3]
    good.sort(key=lambda c: -(c["score"] if c["score"] is not None else -1))
    return good[:MAX_CANDIDATES]


def gather(series, hint, tried, hashes, log, use_ai=True, ai_only=False):
    """Collect validated, de-duplicated candidates, then keep only the ones that match the series."""
    sources = []
    if not ai_only:
        for label, fn in (("Wikidata", wikidata_images), ("Wikipedia", wikipedia_images)):
            try:
                urls = fn(series)
                log(f"{label}: {len(urls)} matching link(s)")
                sources += [(u, label.lower()) for u in urls]
            except Exception as error:
                log(f"{label} lookup failed: {error}")
    if use_ai and OPENAI_API_KEY:
        try:
            ai = ask_ai_for_urls(series, hint, tried)
            log(f"AI returned {len(ai)} link(s)")
            sources += [(u, "ai") for u in ai]
        except Exception as error:
            log(f"AI request failed: {error}")

    sources = [(u, s) for u, s in sources if u not in tried]
    for u, _ in sources:
        tried.add(u)
    with ThreadPoolExecutor(6) as pool:
        futures = [pool.submit(resolve_images, u, s, log) for u, s in sources]
        results = [f.result() for f in futures]
    pool_list = []
    for batch in results:
        for img in batch:
            h = hashlib.md5(img["data"]).hexdigest()
            if h in hashes:
                continue
            hashes.add(h)
            pool_list.append(img)
            if len(pool_list) >= MAX_CANDIDATES * 2:
                break
    return rank_candidates(series, pool_list, log)


# --------------------------------------------------------------------------- #
# Directus
# --------------------------------------------------------------------------- #
def upload_to_directus(title, slug, data, ctype, folder=None):
    ext = mimetypes.guess_extension(ctype) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    if ctype == "image/svg+xml":
        ext = ".svg"
    files = {"file": (f"{slug}{ext}", data, ctype)}
    form = {"title": title}
    if folder:
        form["folder"] = folder
    r = requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS, files=files, data=form, timeout=60)
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
        headers=HEADERS, json={"image": image_id}, timeout=30,
    )
    r.raise_for_status()
    return True


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


def load_brands_file(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return raw.get("data", []) if isinstance(raw, dict) else raw


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": {}, "skipped": []}


def save_progress(p):
    PROGRESS_FILE.write_text(json.dumps(p, indent=2))


# --------------------------------------------------------------------------- #
# Shared state between worker thread and UI server
# --------------------------------------------------------------------------- #
LOCK = threading.Lock()
ACTIONS = queue.Queue()
IMAGES = {}  # token -> (bytes, content_type)
STATE = {
    "status": "starting",  # starting | searching | review | uploading | finished
    "index": 0,
    "total": 0,
    "series": None,
    "items": {},  # asset -> {candidates:[{token,url,type,size,source}], selected, error}
    "log": [],
    "auto_approve": False,
}


def log(msg):
    print("  " + msg, flush=True)
    with LOCK:
        STATE["log"] = (STATE["log"] + [msg])[-14:]


def set_state(**kw):
    with LOCK:
        STATE.update(kw)


# --------------------------------------------------------------------------- #
# Worker: loop over all series
# --------------------------------------------------------------------------- #
def run_worker(args, series_list, progress):
    processed = 0
    try:
        for idx, series in enumerate(series_list):
            if idx < args.start:
                continue
            if args.limit is not None and processed >= args.limit:
                break
            is_dict = isinstance(series, dict)
            series_id = series.get("id") if is_dict else None
            name = (series.get("name") or "series") if is_dict else "invalid record"
            if not series_id:
                print(f"[{idx + 1}/{len(series_list)}] {name}: missing Directus id; skipped")
                continue
            if file_id(series.get("image")) or (str(series_id) in progress["done"] and not args.redo):
                continue
            processed += 1
            print(f"\n[{idx + 1}/{len(series_list)}] {name}")
            IMAGES.clear()
            set_state(status="searching", index=idx + 1, items={}, log=[],
                      series={"id": series_id, "name": name, "context": brand_context(series)})
            try:
                if process_series(args, series, series_id, name, progress) == "quit":
                    break
            except requests.RequestException as error:
                detail = getattr(getattr(error, "response", None), "text", "")
                log(f"Directus request failed: {error} {detail[:200]}")
                time.sleep(2)
            except Exception as error:
                log(f"failed: {error}")
                time.sleep(2)
    finally:
        save_progress(progress)
        set_state(status="finished", series=None, items={})
        print("\nDone. Press Ctrl+C to close the review UI.")


def process_series(args, series, series_id, name, progress):
    current = get_series(series_id)
    if file_id(current.get("image")):
        log("image already set in Directus; skipped")
        progress["done"][str(series_id)] = "already complete"
        save_progress(progress)
        return None

    found, hashes, tried = [], set(), set()
    state = {"preferred": None, "error": None}

    def add(cands, front=False):
        for c in cands:
            c["token"] = uuid.uuid4().hex
            IMAGES[c["token"]] = (c["data"], c["type"])
        found[:] = (cands + found) if front else (found + cands)
        state["error"] = None if found else "No images found. Paste a URL, or ask the AI with a hint."

    def view():
        cl = [{"token": c["token"], "url": c["url"], "type": c["type"],
               "size": len(c["data"]), "source": c["source"],
               "score": c.get("score"), "reason": c.get("reason")} for c in found]
        return {ASSET: {"candidates": cl, "error": state["error"],
                        "selected": state["preferred"] or (cl[0]["token"] if cl else None)}}

    add(gather(series, "", tried, hashes, log, use_ai=not args.no_ai))
    set_state(status="review", items=view())

    while True:
        with LOCK:
            auto = STATE["auto_approve"]
        if auto:
            action = {"action": "approve", "choices": {ASSET: found[0]["token"]} if found else {}}
        else:
            action = ACTIONS.get()

        kind = action.get("action")
        if kind == "quit":
            return "quit"
        if kind == "skip":
            progress.setdefault("skipped", []).append(str(series_id))
            save_progress(progress)
            log("skipped by user")
            return None
        if kind in ("retry", "set_url"):
            set_state(status="searching")
            if kind == "retry":
                new = gather(series, action.get("hint", ""), tried, hashes, log, use_ai=True, ai_only=True)
                log(f"{len(new)} new candidate(s)")
                add(new)
            else:
                url = normalize_url(action.get("url") or "")
                new = resolve_images(url, "pasted", log) if url.startswith("http") else []
                if new:
                    img = new[0]
                    h = hashlib.md5(img["data"]).hexdigest()
                    if h in hashes:
                        state["preferred"] = next(c["token"] for c in found
                                                  if hashlib.md5(c["data"]).hexdigest() == h)
                    else:
                        hashes.add(h)
                        add([img], front=True)
                        state["preferred"] = found[0]["token"]
                else:
                    log("that URL did not return an image")
            set_state(status="review", items=view())
            continue
        if kind == "approve":
            by_token = {c["token"]: c for c in found}
            token = (action.get("choices") or {}).get(ASSET)
            img = by_token.get(token)
            if not img:
                log("nothing selected to upload")
                if auto:
                    progress.setdefault("skipped", []).append(str(series_id))
                    save_progress(progress)
                    return None
                continue
            set_state(status="uploading")
            safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or str(series_id)
            image_id = upload_to_directus(name, safe, img["data"], img["type"], args.folder)
            if patch_series_image(series_id, current.get("image"), image_id):
                log("uploaded and linked image")
                progress["done"][str(series_id)] = {"image": image_id, "src": img["url"]}
            else:
                log("image field already set; nothing linked")
                progress.setdefault("skipped", []).append(str(series_id))
            save_progress(progress)
            return None


# --------------------------------------------------------------------------- #
# Review UI (stdlib http.server, no extra deps)
# --------------------------------------------------------------------------- #
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Series images review</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--bd:#2a2f3a;--tx:#e8eaf0;--mu:#8b93a7;--ac:#4f8cff;--ok:#22c55e;--er:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px system-ui,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header h1{font-size:18px;margin:0}.sp{flex:1}
.bar{height:6px;background:var(--bd);border-radius:4px;overflow:hidden;width:220px}
.bar div{height:100%;background:var(--ac);transition:width .3s}
main{max-width:760px;margin:24px auto;padding:0 24px}
.name{font-size:24px;font-weight:700}.mu{color:var(--mu);font-size:13px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px;margin-top:20px;min-width:0}
.card h3{margin:0 0 10px;display:flex;justify-content:space-between;align-items:center}
.chk{background:repeating-conic-gradient(#2b2f3a 0 25%,#222631 0 50%) 0 0/20px 20px}
.pv{height:340px;border-radius:8px;display:flex;align-items:center;justify-content:center;overflow:hidden}
.pv img{max-width:100%;max-height:100%;object-fit:contain}
.err{color:var(--er);padding:20px;text-align:center;background:var(--card);width:100%}
.url{word-break:break-all;margin:10px 0 4px;font-size:12px;color:var(--mu)}
.thumbs{display:flex;gap:6px;overflow-x:auto;margin-top:10px;padding-bottom:4px}
.th{width:72px;height:72px;flex:none;border:2px solid var(--bd);border-radius:6px;cursor:pointer;overflow:hidden;
display:flex;align-items:center;justify-content:center}
.th img{max-width:100%;max-height:100%}.th.on{border-color:var(--ac)}
.row{display:flex;gap:8px;margin-top:8px;align-items:center}
input[type=text]{flex:1;background:#0f1115;border:1px solid var(--bd);color:var(--tx);border-radius:8px;padding:8px 10px;min-width:0}
button{background:#232838;color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:8px 14px;cursor:pointer;font-size:14px}
button:hover{border-color:var(--ac)}
button.ok{background:var(--ok);border-color:var(--ok);color:#06210f;font-weight:700}
button:disabled{opacity:.5;cursor:not-allowed}
.actions{display:flex;gap:12px;margin-top:22px;align-items:center;flex-wrap:wrap}
.log{margin-top:22px;font:12px ui-monospace,monospace;color:var(--mu);white-space:pre-wrap;word-break:break-all}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--bd);border-top-color:var(--ac);border-radius:50%;animation:s 1s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
.center{text-align:center;margin-top:90px;font-size:18px}
label.ck{font-size:13px;color:var(--mu);display:flex;gap:6px;align-items:center;font-weight:400}
</style></head><body>
<header><h1>Series images review</h1><div class="bar"><div id="bar"></div></div><span class="mu" id="cnt"></span>
<span class="sp"></span><label class="ck"><input type="checkbox" id="auto"> Auto-approve (first candidate, no review)</label></header>
<main id="m"><div class="center"><span class="spin"></span>Starting…</div></main>
<script>
let last="",sel={},lastSrv={};
const A="image";
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function act(o){await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(o)});}
function meta(c){if(!c)return "";const sc=c.score!=null?` · <span style="color:${c.score>=6?"#22c55e":"#ef4444"}">match ${c.score}/10 (${esc(c.reason)})</span>`:"";return `${esc(c.source)} · ${esc(c.type)} · ${(c.size/1024).toFixed(0)} KB${sc}`;}
function card(it){
  const cs=it.candidates||[], cur=cs.find(x=>x.token===sel[A])||cs[0];
  const pv=cur?`<img src="/img/${cur.token}">`:`<div class="err">${esc(it.error||"No image")}</div>`;
  return `<div class="card"><h3><span>Image</span>
   ${cur?`<label class="ck"><input type="checkbox" class="sel" checked> upload</label>`:""}</h3>
   <div class="pv ${cur?"chk":""}">${pv}</div>
   <div class="url"><span class="u">${esc(cur?.url||"")}</span> <b class="mt">${meta(cur)}</b></div>
   <div class="thumbs">${cs.map(c=>`<div class="th chk ${cur&&c.token===cur.token?"on":""}" data-t="${c.token}"><img src="/img/${c.token}"></div>`).join("")}</div>
   <div class="row"><button class="google">Search Google Images</button>
   <span class="mu">Right-click an image → “Copy image address” → paste below.</span></div>
   <div class="row"><input type="text" class="hint" placeholder="Hint for AI (optional), e.g. 'front view, white background'">
   <button class="retry">Find more (AI)</button></div>
   <div class="row"><input type="text" class="url2" placeholder="Paste an image URL or page URL">
   <button class="seturl">Use</button></div></div>`;
}
function render(s){
  $("#cnt").textContent=s.total?`${s.index}/${s.total}`:"";
  $("#bar").style.width=s.total?(100*s.index/s.total)+"%":"0";
  $("#auto").checked=s.auto_approve;
  const m=$("#m");
  if(s.status==="finished"){m.innerHTML='<div class="center">✅ Finished. You can close this tab.</div>';return;}
  if(!s.series){m.innerHTML='<div class="center"><span class="spin"></span>Starting…</div>';return;}
  const key=JSON.stringify([s.status,s.series.id,s.items]);
  if(key===last){const l=$("#log");if(l)l.textContent=s.log.join("\n");return;} last=key;
  const it=s.items[A]||{candidates:[]}, cs=it.candidates||[];
  if(it.selected!==lastSrv[A]){sel[A]=it.selected;lastSrv[A]=it.selected;}
  if(!cs.find(x=>x.token===sel[A]))sel[A]=cs[0]?.token;
  const busy=s.status==="searching"||s.status==="uploading";
  const label=s.status==="uploading"?"Uploading…":"Searching + validating images…";
  m.innerHTML=`<div class="name">${esc(s.series.name)}</div><div class="mu">${esc(s.series.context||"")}</div>
   ${busy?`<div class="mu" style="margin-top:10px"><span class="spin"></span>${label}</div>`:""}
   ${card(it)}
   <div class="actions"><button class="ok" id="ap" ${busy?"disabled":""}>Approve &amp; upload</button>
   <button id="sk" ${busy?"disabled":""}>Skip series</button><button id="qt">Quit</button></div>
   <div class="log" id="log">${esc(s.log.join("\n"))}</div>`;
  const c=m.querySelector(".card");
  c.querySelectorAll(".th").forEach(t=>t.onclick=()=>{
    sel[A]=t.dataset.t; const cand=cs.find(x=>x.token===sel[A]);
    c.querySelector(".pv img").src="/img/"+sel[A];
    c.querySelector(".u").textContent=cand.url; c.querySelector(".mt").innerHTML=meta(cand);
    c.querySelectorAll(".th").forEach(x=>x.classList.toggle("on",x===t));
  });
  c.querySelector(".google").onclick=()=>{
    const q=`${s.series.context?s.series.context+" ":""}${s.series.name} product image`;
    window.open("https://www.google.com/search?tbm=isch&q="+encodeURIComponent(q),"_blank","noopener");};
  c.querySelector(".retry").onclick=()=>act({action:"retry",hint:c.querySelector(".hint").value});
  c.querySelector(".seturl").onclick=()=>act({action:"set_url",url:c.querySelector(".url2").value});
  $("#ap").onclick=()=>{const k=c.querySelector(".sel"),choices={};
    if(k&&k.checked&&sel[A])choices[A]=sel[A]; act({action:"approve",choices});};
  $("#sk").onclick=()=>act({action:"skip"});
  $("#qt").onclick=()=>{if(confirm("Quit?"))act({action:"quit"});};
}
$("#auto").onchange=e=>fetch("/api/auto",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({value:e.target.checked})});
async function poll(){try{const r=await fetch("/api/state");render(await r.json());}catch(e){}setTimeout(poll,900);}
poll();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with LOCK:
                self._send(200, json.dumps(STATE))
        elif self.path.startswith("/img/"):
            got = IMAGES.get(self.path[5:])
            if got:
                self._send(200, got[0], got[1])
            else:
                self._send(404, "not found", "text/plain")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, '{"ok":false}')
        if self.path == "/api/action":
            ACTIONS.put(data)
        elif self.path == "/api/auto":
            set_state(auto_approve=bool(data.get("value")))
            if data.get("value"):
                ACTIONS.put({"action": "noop"})  # wake worker if it is waiting
        else:
            return self._send(404, '{"ok":false}')
        self._send(200, '{"ok":true}')


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "cataloge content", "series.json"),
                    help="local series JSON export")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, help="maximum series to process")
    ap.add_argument("--folder", default=None, help="Directus folder id for uploads")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--auto-approve", action="store_true",
                    help="upload the first candidate without waiting for review")
    ap.add_argument("--no-ai", action="store_true",
                    help="skip OpenAI; use only Wikidata + Wikipedia (free)")
    ap.add_argument("--brands-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                           "cataloge content", "brands.json"),
                    help="brands JSON export, used to turn a series' brand id into a brand name")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the AI relevance check (more unrelated images will appear)")
    ap.add_argument("--min-score", type=int, default=6, help="minimum 0-10 relevance score (default 6)")
    ap.add_argument("--redo", action="store_true", help="re-process series already in the progress file")
    ap.add_argument("--no-browser", action="store_true", help="do not auto-open the review UI")
    args = ap.parse_args()

    if not DIRECTUS_TOKEN:
        ap.error("Set DIRECTUS_TOKEN in the environment or .env file")
    if not OPENAI_API_KEY and not args.no_ai:
        ap.error("Set OPENAI_API_KEY in the environment or .env file (or use --no-ai)")
    try:
        series_list = load_series(args.file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        ap.error(str(error))
    progress = load_progress()
    print(f"Loaded {len(series_list)} series from {args.file}")

    global VERIFY, MIN_SCORE
    VERIFY, MIN_SCORE = not args.no_verify, args.min_score
    try:
        for b in load_brands_file(args.brands_file):
            if isinstance(b, dict) and b.get("id") is not None:
                tr = b.get("translations") or [{}]
                nm = b.get("name") or (tr[0].get("name") if isinstance(tr[0], dict) else None)
                if nm:
                    BRAND_NAMES[str(b["id"])] = str(nm)
        print(f"Loaded {len(BRAND_NAMES)} brand names for search context")
    except (OSError, ValueError, json.JSONDecodeError):
        print("No brands file found; searching by series name only (pass --brands-file for better matches)")

    set_state(total=len(series_list), auto_approve=args.auto_approve)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Review UI: {url}")
    if not args.no_browser:
        webbrowser.open(url)

    threading.Thread(target=run_worker, args=(args, series_list, progress), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        save_progress(progress)
        print("\nInterrupted. Progress saved; run again to resume.")
        sys.exit(0)


if __name__ == "__main__":
    main()