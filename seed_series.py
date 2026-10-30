#!/usr/bin/env python3
"""
seed_series.py
Loop over every brand in Directus, ask OpenAI (model configurable, default "luna-6")
for the REAL series of that brand, skip the ones that already exist in `series`,
build the full object (7 translations), validate it, and POST it to Directus.

Relations (from the JSON structure):
  categories 1--n subcategories 1--n series 1--n models 1--n models_attribute_values
  brands n--n categories ; series.brand_id -> brands ; series.subcategory_id -> subcategories

Usage:
  export DIRECTUS_URL="https://dev-dashboard.swibba.com"
  export DIRECTUS_TOKEN="<static token, without the word Bearer>"
  export OPENAI_API_KEY="sk-..."
  export OPENAI_MODEL="luna-6"            # exact model id of your provider
  # export OPENAI_BASE_URL="https://api.openai.com/v1"   # change if your provider differs

  python seed_series.py --dry-run                 # nothing is written
  python seed_series.py                           # real run
  python seed_series.py --brand toyota --brand nike
  python seed_series.py --start-after-brand toyota
  python seed_series.py --brands-file "brands_validation.json"
  python seed_series.py --limit 10
"""
import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Graceful fallback to load .env if python-dotenv is not installed in the environment
    _env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env_file):
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip().strip("'\"")
                    if _k and _k not in os.environ:
                        os.environ[_k] = _v

# --------------------------------------------------------------------------- config
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://dev-dashboard.swibba.com").rstrip("/")
DIRECTUS_TOKEN = (os.getenv("DIRECTUS_TOKEN") or "x46IAO9d7cHVxLKb13VPLzVDclHPLsED").replace("Bearer ", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

CURRENT_YEAR = datetime.now().year
DEFAULT_YEARS = (2016, CURRENT_YEAR)
AUTOMOTIVE_YEARS = (2000, CURRENT_YEAR)
AUTOMOTIVE_HINTS = ("automotive", "auto", "car", "cars", "vehicle", "vehicles", "motorcycle", "truck")

LANGS = ["en-US", "ar-SA", "fr-FR", "es-ES", "it-IT", "hi-IN", "ru-RU"]
SCRIPT_CHECK = {  # script each translation must be written in (None = latin, no check)
    "ar-SA": re.compile(r"[\u0600-\u06FF]"),
    "hi-IN": re.compile(r"[\u0900-\u097F]"),
    "ru-RU": re.compile(r"[\u0400-\u04FF]"),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_series")


# --------------------------------------------------------------------------- http
def make_session():
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=None)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


SESSION = make_session()


def directus(method, path, **kw):
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}", "Content-Type": "application/json"}
    r = SESSION.request(method, f"{DIRECTUS_URL}{path}", headers=headers, timeout=60, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"Directus {method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json().get("data")


def dget(collection, params=None):
    p = {"limit": -1}
    p.update(params or {})
    return directus("GET", f"/items/{collection}", params=p) or []


# --------------------------------------------------------------------------- openai
def llm_json(system, user, retries=3):
    """Call the chat-completions endpoint and return parsed JSON."""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=body, timeout=180)
            if r.status_code >= 400:
                raise RuntimeError(f"LLM {r.status_code}: {r.text[:400]}")
            txt = r.json()["choices"][0]["message"]["content"]
            txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
            return json.loads(txt)
        except Exception as e:  # noqa
            last = e
            log.warning("LLM attempt %s/%s failed: %s", attempt, retries, e)
            time.sleep(2 * attempt)
    raise RuntimeError(f"LLM failed: {last}")


# --------------------------------------------------------------------------- helpers
def slugify(text):
    """Unicode-aware slug (keeps Arabic / Hindi / Cyrillic letters), like the example in the spec."""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def norm(name):
    return re.sub(r"[^a-z0-9\u0600-\u06FF]", "", str(name).lower())


def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def years_for(brand_categories):
    """Use 2000-present for automotive brands and 2016-present for others."""
    for c in brand_categories:
        text = f"{c.get('name','')} {c.get('slug','')}".lower()
        if any(h in re.split(r"[\s\-_/&,]+", text) or h in text for h in AUTOMOTIVE_HINTS):
            return AUTOMOTIVE_YEARS
    return DEFAULT_YEARS


# --------------------------------------------------------------------------- load structure
def load_structure():
    categories = {c["id"]: c for c in dget("categories", {"fields": "id,name,slug,description,category_type"})}
    categories_by_name = {norm(c.get("name", "")): c for c in categories.values() if c.get("name")}
    subs_raw = dget("subcategories", {"fields": "*"})
    subs = {}
    for s in subs_raw:
        cat_id = pick(s, "category_id", "category", "categories_id", "parent_id")
        if isinstance(cat_id, dict):
            cat_id = cat_id.get("id")
        s["_category_id"] = cat_id
        subs[s["id"]] = s
    return categories, categories_by_name, subs


def load_brands(path, categories, categories_by_name):
    with open(path, "r", encoding="utf-8-sig") as stream:
        source = json.load(stream)
    brands = source.get("data", []) if isinstance(source, dict) else source
    if not isinstance(brands, list) or any(
        not isinstance(brand, dict) or not brand.get("id") or not brand.get("name")
        for brand in brands
    ):
        raise ValueError("brand input must be a list (or contain a data list) of records with id and name")

    directus_brands = dget(
        "brands", {"fields": "id,name,slug,description,country,year_founded,categories.*"}
    )
    directus_by_id = {str(brand["id"]): brand for brand in directus_brands if brand.get("id")}
    directus_by_name = {norm(brand.get("name", "")): brand for brand in directus_brands if brand.get("name")}

    for brand in brands:
        directus_brand = directus_by_id.get(str(brand["id"])) or directus_by_name.get(norm(brand["name"]))
        # Keep the selected JSON record authoritative while using Directus to fill missing fields/relations.
        combined = {**(directus_brand or {}), **brand}
        if not combined.get("categories") and directus_brand:
            combined["categories"] = directus_brand.get("categories", [])
        brand.clear()
        brand.update(combined)

        resolved_categories = []
        for junction in brand.get("categories") or []:
            value = pick(junction, "categories_id", "category_id", "categories") if isinstance(junction, dict) else junction
            if isinstance(value, dict):
                category = categories.get(value.get("id")) or categories_by_name.get(norm(value.get("name", "")))
            else:
                category = categories.get(value) or categories_by_name.get(norm(value))
            if category and category.get("id") not in resolved_categories:
                resolved_categories.append(category["id"])
        brand["_category_ids"] = resolved_categories

    return brands


def brand_category_ids(brand):
    """brands.categories is an M2M list of junction rows (e.g. 781); resolve to category uuids."""
    if "_category_ids" in brand:
        return brand["_category_ids"]
    out = []
    for j in brand.get("categories") or []:
        if isinstance(j, dict):
            cid = pick(j, "categories_id", "category_id", "categories")
            if isinstance(cid, dict):
                cid = cid.get("id")
            if cid:
                out.append(cid)
    return out


# --------------------------------------------------------------------------- step 1: discover series names
DISCOVER_SYSTEM = (
    "You are a meticulous product-catalog researcher. You only output REAL, officially named product "
    "series / product lines / model families that were actually released by the given brand. "
    "Never invent names. If unsure, leave it out. Reply with JSON only."
)


def discover_series(brand, cats, subs, y_from, y_to):
    payload = {
        "brand": {k: brand.get(k) for k in ("name", "country", "year_founded", "description")},
        "categories": [{"name": c["name"], "description": c.get("description")} for c in cats],
        "allowed_subcategories": [{"id": s["id"], "name": s["name"]} for s in subs],
        "year_range": [y_from, y_to],
    }
    found = []
    seen = set()
    for year in range(y_from, y_to + 1):
        year_payload = {**payload, "year_range": [year, year]}
        user = (
            "List every real, officially named series/product line/model family for this brand that was first "
            f"released or had a new generation launched in {year}, within the brand's categories. Include "
            "discontinued and legacy lines when they had a release in this year; do not limit the answer to "
            "popular/current products. Do not invent or repeat items with no release in this year. For each "
            "item choose the single best subcategory id from allowed_subcategories (copy it exactly), use its "
            "official English name, and set release_year to this year.\n"
            '{"series":[{"name":"","subcategory_id":"","release_year":'
            f'{year}' + "}]}\n\n"
            + json.dumps(year_payload, ensure_ascii=False)
        )
        data = llm_json(DISCOVER_SYSTEM, user)
        items = data.get("series") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = norm(item.get("name", ""))
            if key and key not in seen:
                seen.add(key)
                found.append(item)
    return found


# --------------------------------------------------------------------------- step 2: build full object
BUILD_SYSTEM = (
    "You are a multilingual catalog editor. Produce accurate, factual, non-marketing product copy. "
    "Everything must be true for the real product series. Reply with JSON only."
)


def build_series(brand, sub, name, year):
    user = (
        f"Brand: {brand['name']}\nSeries: {name}\nSubcategory: {sub['name']}\nRelease year: {year}\n\n"
        "Write a factual 1-2 sentence description of this series (what it is, key purpose/traits) and "
        "translate name + description into these locales: " + ", ".join(LANGS) + ".\n"
        "Rules: keep brand/series names in Latin script for en-US, fr-FR, es-ES, it-IT; transliterate/translate "
        "naturally into Arabic (ar-SA), Devanagari (hi-IN) and Cyrillic (ru-RU) as in common usage. "
        "Do not add specs you are not sure about.\n"
        'Return: {"description":"","translations":[{"languages_code":"en-US","name":"","description":""}, ...]}'
    )
    data = llm_json(BUILD_SYSTEM, user)
    return data


def assemble(brand, sub, name, year, llm):
    translations = []
    by_code = {t.get("languages_code"): t for t in llm.get("translations", []) if isinstance(t, dict)}
    for code in LANGS:
        t = by_code.get(code, {})
        n = (t.get("name") or "").strip()
        d = (t.get("description") or "").strip()
        translations.append({"languages_code": code, "name": n, "description": d, "slug": slugify(n)})
    return {
        "status": "active",
        "brand_id": brand["id"],
        "subcategory_id": sub["id"],
        "name": name.strip(),
        "slug": slugify(name),
        "description": (llm.get("description") or "").strip(),
        "release_year": int(year),
        "translations": translations,
    }


# --------------------------------------------------------------------------- validation
def validate(obj, allowed_sub_ids, y_from, y_to):
    errs = []
    for k in ("status", "brand_id", "subcategory_id", "name", "slug", "description", "release_year", "translations"):
        if obj.get(k) in (None, "", []):
            errs.append(f"missing {k}")
    if errs:
        return errs
    if obj["subcategory_id"] not in allowed_sub_ids:
        errs.append("subcategory not allowed for this brand")
    if not (y_from <= obj["release_year"] <= y_to):
        errs.append(f"release_year {obj['release_year']} outside {y_from}-{y_to}")
    if len(obj["description"]) < 20:
        errs.append("description too short")
    codes = [t["languages_code"] for t in obj["translations"]]
    if sorted(codes) != sorted(LANGS):
        errs.append(f"translations must be exactly {LANGS}")
    for t in obj["translations"]:
        c = t["languages_code"]
        if not t["name"] or not t["description"] or not t["slug"]:
            errs.append(f"{c}: empty name/description/slug")
            continue
        chk = SCRIPT_CHECK.get(c)
        if chk and not (chk.search(t["name"]) and chk.search(t["description"])):
            errs.append(f"{c}: text not written in expected script")
        if c in ("en-US",) and norm(t["name"]) != norm(obj["name"]):
            errs.append("en-US name differs from main name")
    return errs


VERIFY_SYSTEM = "You are a strict fact-checker for product catalogs. Reply with JSON only."


def verify_real(brand, obj, sub):
    """Second LLM pass: does this series really exist for this brand and year?"""
    user = (
        f"Does the product series '{obj['name']}' really exist as an official series/product line of the brand "
        f"'{brand['name']}' (subcategory: {sub['name']}), released/launched in {obj['release_year']}? "
        'Return {"exists":true|false,"confidence":0-1,"reason":""}.'
    )
    try:
        r = llm_json(VERIFY_SYSTEM, user, retries=2)
        return bool(r.get("exists")) and float(r.get("confidence", 0)) >= 0.7, r.get("reason", "")
    except Exception as e:  # noqa
        return False, f"verification failed: {e}"


# --------------------------------------------------------------------------- main loop
def main():
    global OPENAI_MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="do everything except POST")
    ap.add_argument("--brand", action="append", help="brand slug/name to process (repeatable)")
    ap.add_argument("--start-after-brand", help="resume after this brand slug/name")
    ap.add_argument(
        "--brands-file",
        default=os.path.join(os.path.dirname(__file__), "cataloge content", "brands.json"),
        help="JSON file containing brands to process (default: cataloge content/brands.json)",
    )
    ap.add_argument("--limit", type=int, help="max number of brands")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--model", help=f"OpenAI model to use (default: {OPENAI_MODEL})")
    ap.add_argument("--report", help="path or filename for the JSON report output")
    args = ap.parse_args()

    if args.model:
        OPENAI_MODEL = args.model

    if not DIRECTUS_TOKEN or not OPENAI_API_KEY:
        sys.exit("Set DIRECTUS_TOKEN and OPENAI_API_KEY environment variables.")

    try:
        categories, categories_by_name, subs = load_structure()
        brands = load_brands(args.brands_file, categories, categories_by_name)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        ap.error(f"could not load brands or Directus structure: {error}")
    log.info("Loaded %s categories, %s subcategories, %s brands", len(categories), len(subs), len(brands))

    if args.brand:
        wanted = {b.lower() for b in args.brand}
        brands = [b for b in brands if (b.get("slug") or "").lower() in wanted or (b.get("name") or "").lower() in wanted]
    if args.start_after_brand:
        start_after = args.start_after_brand.lower()
        matches = [
            i for i, brand in enumerate(brands)
            if start_after in ((brand.get("slug") or "").lower(), (brand.get("name") or "").lower())
        ]
        if len(matches) != 1:
            ap.error(f"--start-after-brand must match exactly one selected brand; found {len(matches)}")
        brands = brands[matches[0] + 1:]
    if args.limit:
        brands = brands[: args.limit]

    all_series = dget("series", {"fields": "id,name,slug,brand_id,subcategory_id"})
    used_slugs = {s["slug"] for s in all_series if s.get("slug")}
    report = {"created": [], "skipped_existing": [], "rejected": [], "errors": []}

    for i, brand in enumerate(brands, 1):
        log.info("[%s/%s] Brand: %s", i, len(brands), brand.get("name"))
        try:
            cat_ids = brand_category_ids(brand)
            brand_cats = [categories[c] for c in cat_ids if c in categories]
            brand_subs = [s for s in subs.values() if s["_category_id"] in cat_ids]
            if not brand_cats or not brand_subs:
                log.warning("  no categories/subcategories resolved for %s - skipped", brand.get("name"))
                report["errors"].append({"brand": brand.get("name"), "error": "no categories/subcategories"})
                continue

            y_from, y_to = years_for(brand_cats)
            allowed = {s["id"]: s for s in brand_subs}

            found = discover_series(brand, brand_cats, brand_subs, y_from, y_to)
            log.info("  LLM returned %s series (%s-%s)", len(found), y_from, y_to)

            existing = {norm(s["name"]) for s in all_series if s.get("brand_id") == brand["id"]}

            for item in found:
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                if norm(name) in existing:
                    report["skipped_existing"].append({"brand": brand["name"], "series": name})
                    log.info("  = exists: %s", name)
                    continue
                sub = allowed.get(item.get("subcategory_id"))
                if not sub:
                    report["rejected"].append({"brand": brand["name"], "series": name, "why": "bad subcategory_id"})
                    continue
                try:
                    year = int(item.get("release_year"))
                except (TypeError, ValueError):
                    report["rejected"].append({"brand": brand["name"], "series": name, "why": "bad year"})
                    continue

                obj, errs = None, ["not built"]
                for attempt in range(3):
                    obj = assemble(brand, sub, name, year, build_series(brand, sub, name, year))
                    errs = validate(obj, set(allowed), y_from, y_to)
                    if not errs:
                        break
                    log.warning("  validation retry %s for %s: %s", attempt + 1, name, errs)
                if errs:
                    report["rejected"].append({"brand": brand["name"], "series": name, "why": errs})
                    continue

                ok, reason = verify_real(brand, obj, sub)
                if not ok:
                    report["rejected"].append({"brand": brand["name"], "series": name, "why": f"not verified: {reason}"})
                    log.warning("  x rejected (not verified): %s", name)
                    continue

                if obj["slug"] in used_slugs:
                    obj["slug"] = f"{obj['slug']}-{slugify(brand['name'])}"
                    obj["translations"][0]["slug"] = obj["slug"]

                if args.dry_run:
                    log.info("  ~ dry-run would create: %s", name)
                else:
                    created = directus("POST", "/items/series", json=obj)
                    log.info("  + created: %s (%s)", name, created.get("id"))
                    all_series.append({"id": created.get("id"), "name": name, "slug": obj["slug"],
                                       "brand_id": brand["id"], "subcategory_id": sub["id"]})
                used_slugs.add(obj["slug"])
                existing.add(norm(name))
                report["created"].append(obj)
                time.sleep(args.sleep)

        except Exception as e:  # noqa
            log.exception("  brand failed: %s", brand.get("name"))
            report["errors"].append({"brand": brand.get("name"), "error": str(e)})

    out = args.report or f"series_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log.info("Done. created=%s existing=%s rejected=%s errors=%s -> %s",
             len(report["created"]), len(report["skipped_existing"]),
             len(report["rejected"]), len(report["errors"]), out)


if __name__ == "__main__":
    main()