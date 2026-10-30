#!/usr/bin/env python3
"""Discover real brands for catalog categories and seed missing brands in Directus.

Usage:
  Set DIRECTUS_TOKEN and OPENAI_API_KEY in the environment or .env file.
  python seed_brands.py --dry-run
  python seed_brands.py --category automotive --limit 20
  python seed_brands.py
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
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value

DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://dev-dashboard.swibba.com").rstrip("/")
DIRECTUS_TOKEN = (os.getenv("DIRECTUS_TOKEN") or "").replace("Bearer ", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LANGS = ["en-US", "ar-SA", "fr-FR", "es-ES", "it-IT", "hi-IN", "ru-RU"]
SEARCH_REGIONS = (
    "East Asia and Southeast Asia",
    "South Asia and Central Asia",
    "Europe",
    "North America and Latin America",
    "Middle East and Africa",
)
SCRIPT_CHECK = {
    "ar-SA": re.compile(r"[\u0600-\u06FF]"),
    "hi-IN": re.compile(r"[\u0900-\u097F]"),
    "ru-RU": re.compile(r"[\u0400-\u04FF]"),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_brands")


def make_session():
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=None,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


SESSION = make_session()


def directus(method, path, **kwargs):
    headers = {
        "Authorization": f"Bearer {DIRECTUS_TOKEN}",
        "Content-Type": "application/json",
    }
    response = SESSION.request(
        method, f"{DIRECTUS_URL}{path}", headers=headers, timeout=60, **kwargs
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Directus {method} {path} -> {response.status_code}: {response.text[:500]}"
        )
    return response.json().get("data")


def dget(collection, params=None):
    query = {"limit": -1}
    query.update(params or {})
    return directus("GET", f"/items/{collection}", params=query) or []


def llm_json(system, user, retries=3):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = SESSION.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=body,
                timeout=180,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"LLM {response.status_code}: {response.text[:400]}")
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
            return json.loads(content)
        except Exception as error:
            last_error = error
            log.warning("LLM attempt %s/%s failed: %s", attempt, retries, error)
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"LLM failed: {last_error}")


def slugify(text):
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def norm(name):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", str(name)).casefold())


def load_categories(path):
    with open(path, "r", encoding="utf-8-sig") as stream:
        payload = json.load(stream)
    categories = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(categories, list):
        raise ValueError("Category file must contain a list or an object with a data list")
    return [
        category
        for category in categories
        if category.get("id") and category.get("name")
    ]


DISCOVER_SYSTEM = (
    "You are a careful global brand researcher. Return only real, established brand names "
    "that make or provide products/services genuinely relevant to the supplied category and "
    "subcategories. Include brands from different countries, not just the US. Never invent "
    "brands or facts. Return JSON only."
)


def discover_brands(category, subcategories, region=None, max_results=50):
    payload = {
        "category": {
            "name": category["name"],
            "description": category.get("description", ""),
        },
        "subcategories": [
            {"id": sub.get("id"), "name": sub.get("name")}
            for sub in subcategories
            if sub.get("id") and sub.get("name")
        ],
    }
    scope = (
        f"Focus specifically on brands whose products fit {subcategories[0]['name']}. "
        if len(subcategories) == 1
        else "Cover the full range of supplied subcategories. "
    )
    region_scope = (
        f"Prioritize brands founded in, based in, or especially prominent in {region}. "
        "Include local and regional brands, not only multinationals. "
        if region
        else "Deliberately cover brands from different countries and regions. "
    )
    user = (
        f"Find up to {max_results} distinct real brands for this catalog category. "
        + scope
        + region_scope
        + "Include manufacturers, product brands, and important local brands; avoid "
        "duplicates, generic product types, and retailers unless the retailer itself owns "
        "a relevant brand. For each brand provide its official name and the IDs of supplied "
        "subcategories it is genuinely relevant to. Copy IDs exactly. Return as many "
        "well-known relevant brands as you can support; do not pad the list with guesses. "
        "Return {\"brands\":[{\"name\":\"\",\"subcategory_ids\":[\"...\"]}]}\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    result = llm_json(DISCOVER_SYSTEM, user)
    brands = result.get("brands") if isinstance(result, dict) else None
    return brands if isinstance(brands, list) else []


BUILD_SYSTEM = (
    "You are a fact-focused multilingual brand catalog editor. Use accurate, verifiable "
    "facts about real companies, not promotional inventions. Keep brand contact fields "
    "factual; use an official public contact address if known, otherwise an empty string. "
    "Return JSON only."
)


def build_brand(name, category_names):
    user = (
        f"Brand: {name}\nRelevant catalog categories: {', '.join(category_names)}\n\n"
        "Provide factual base information: concise description, official website URL, country "
        "of origin, and year founded. Then provide complete translations in these locales: "
        + ", ".join(LANGS)
        + ". Each translation must include languages_code, name, description, tagline, "
        "short_description, about_us, mission, vision, contact_info, support_info, meta_title, "
        "and meta_description. Translate naturally. Keep the official brand name in Latin "
        "script for en-US, fr-FR, es-ES, it-IT; use normal local-script rendering for Arabic, "
        "Hindi, and Russian. Do not invent company missions, visions, taglines, or email "
        "addresses; use empty strings for unknown copy/contact details. English translation "
        "name must exactly match the official brand name. Return this shape: "
        "{\"description\":\"\",\"website\":\"https://...\",\"country\":\"\","
        "\"year_founded\":1900,\"translations\":[{\"languages_code\":\"en-US\","
        "\"name\":\"\",\"description\":\"\",\"tagline\":\"\","
        "\"short_description\":\"\",\"about_us\":\"\",\"mission\":\"\","
        "\"vision\":\"\",\"contact_info\":\"\",\"support_info\":\"\","
        "\"meta_title\":\"\",\"meta_description\":\"\"}, ...]}"
    )
    return llm_json(BUILD_SYSTEM, user)


VERIFY_SYSTEM = "You are a strict independent fact-checker. Reply with JSON only."


def verify_brand(name, details):
    user = (
        "Independently check whether this is a real brand and whether its supplied details "
        "are substantially accurate. Do not assume the supplied claims are true. "
        f"Brand name: {name}\nDetails: {json.dumps(details, ensure_ascii=False)}\n"
        'Return {"is_real":true,"confidence":0.0,"reason":""}. Set is_real false '
        "or confidence below 0.8 if uncertain or materially inaccurate."
    )
    result = llm_json(VERIFY_SYSTEM, user, retries=2)
    return (
        isinstance(result, dict)
        and result.get("is_real") is True
        and float(result.get("confidence", 0)) >= 0.8,
        result.get("reason", "") if isinstance(result, dict) else "invalid verification response",
    )


TRANSLATION_FIELDS = (
    "name",
    "description",
    "tagline",
    "short_description",
    "about_us",
    "mission",
    "vision",
    "contact_info",
    "support_info",
    "meta_title",
    "meta_description",
)


def validate_details(name, details):
    errors = []
    if not isinstance(details, dict):
        return ["brand details must be an object"]
    for field in ("description", "website", "country", "year_founded"):
        if details.get(field) in (None, ""):
            errors.append(f"missing {field}")
    if details.get("description") and len(details["description"].strip()) < 20:
        errors.append("description too short")
    website = details.get("website", "")
    if website:
        parsed = urlparse(website)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append("website must be an absolute http(s) URL")
    try:
        year = int(details.get("year_founded"))
        if not (1 <= year <= datetime.now().year):
            errors.append("year_founded outside valid range")
        details["year_founded"] = year
    except (TypeError, ValueError):
        errors.append("year_founded must be an integer")

    translations = details.get("translations")
    if not isinstance(translations, list):
        return errors + ["translations must be a list"]
    codes = [
        translation.get("languages_code")
        for translation in translations
        if isinstance(translation, dict)
    ]
    if sorted(codes) != sorted(LANGS):
        errors.append(f"translations must contain exactly these locales: {LANGS}")
    by_code = {
        translation.get("languages_code"): translation
        for translation in translations
        if isinstance(translation, dict)
    }
    for code in LANGS:
        translation = by_code.get(code)
        if not translation:
            continue
        for field in TRANSLATION_FIELDS:
            if not isinstance(translation.get(field), str):
                errors.append(f"{code}: missing or invalid {field}")
        for field in ("name", "description"):
            if isinstance(translation.get(field), str) and not translation[field].strip():
                errors.append(f"{code}: empty {field}")
        if code == "en-US" and translation.get("name") != name:
            errors.append("en-US name differs from official brand name")
        checker = SCRIPT_CHECK.get(code)
        if checker and any(
            translation.get(field) and not checker.search(translation[field])
            for field in ("name", "description")
        ):
            errors.append(f"{code}: name/description not in expected script")
    return errors


def assemble(name, category_ids, details):
    translations = []
    for translation in details["translations"]:
        item = {
            field: (translation.get(field) or "").strip()
            for field in TRANSLATION_FIELDS
        }
        item["languages_code"] = translation["languages_code"]
        item["slug"] = slugify(item["name"])
        translations.append(item)
    return {
        "status": "approved",
        "name": name.strip(),
        "slug": slugify(name),
        "description": details["description"].strip(),
        "website": details["website"].strip(),
        "country": details["country"].strip(),
        "year_founded": int(details["year_founded"]),
        "categories": [{"categories_id": category_id} for category_id in category_ids],
        "translations": translations,
    }


def main():
    global OPENAI_MODEL
    parser = argparse.ArgumentParser(description="Discover and seed real catalog brands")
    parser.add_argument("--dry-run", action="store_true", help="do everything except POST")
    parser.add_argument("--category", action="append", help="category slug/name (repeatable)")
    parser.add_argument("--limit", type=int, help="maximum number of new brands to process")
    parser.add_argument(
        "--max-results-per-search",
        type=int,
        default=50,
        help="requested brand candidates per AI discovery pass (default: 50)",
    )
    parser.add_argument(
        "--no-regional-search",
        action="store_true",
        help="skip additional region-focused discovery passes",
    )
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--model", help=f"OpenAI model to use (default: {OPENAI_MODEL})")
    parser.add_argument(
        "--categories-file",
        default=os.path.join(os.path.dirname(__file__), "cataloge content", "categories.json"),
        help="JSON category data including subcategories",
    )
    args = parser.parse_args()
    if args.model:
        OPENAI_MODEL = args.model
    if args.max_results_per_search < 1:
        parser.error("--max-results-per-search must be greater than zero")
    if not DIRECTUS_TOKEN or not OPENAI_API_KEY:
        sys.exit("Set DIRECTUS_TOKEN and OPENAI_API_KEY environment variables.")

    categories = load_categories(args.categories_file)
    if args.category:
        wanted = {value.casefold() for value in args.category}
        categories = [
            category
            for category in categories
            if category.get("slug", "").casefold() in wanted
            or category["name"].casefold() in wanted
        ]
    if not categories:
        sys.exit("No matching categories found.")

    report = {"created": [], "skipped_existing": [], "rejected": [], "errors": []}
    try:
        existing_brands = dget("brands", {"fields": "id,name,slug"})
    except Exception as error:
        sys.exit(f"Could not load existing Directus brands: {error}")
    existing_names = {norm(brand.get("name", "")) for brand in existing_brands}

    candidates = {}
    for category in categories:
        log.info("Discovering brands for category: %s", category["name"])
        subcategories = {
            subcategory["id"]: subcategory
            for subcategory in category.get("subcategories", [])
            if subcategory.get("id")
        }
        all_subcategories = list(subcategories.values())
        search_scopes = [("category", all_subcategories, None)]
        search_scopes.extend(
            ("subcategory", [subcategory], None)
            for subcategory in all_subcategories
        )
        if not args.no_regional_search:
            search_scopes.extend(
                ("region", all_subcategories, region)
                for region in SEARCH_REGIONS
            )

        for scope_name, scoped_subcategories, region in search_scopes:
            scope_label = region or (
                scoped_subcategories[0]["name"]
                if scope_name == "subcategory"
                else "all subcategories"
            )
            try:
                found = discover_brands(
                    category,
                    scoped_subcategories,
                    region=region,
                    max_results=args.max_results_per_search,
                )
                log.info("  %s pass '%s': %s candidates", scope_name, scope_label, len(found))
            except Exception as error:
                log.exception("Discovery failed for %s / %s", category["name"], scope_label)
                report["errors"].append(
                    {"category": category["name"], "scope": scope_label, "error": str(error)}
                )
                continue

            for item in found:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                key = norm(name)
                if not key:
                    continue
                candidate = candidates.setdefault(
                    key, {"name": name, "category_ids": set(), "subcategories": set()}
                )
                requested_sub_ids = item.get("subcategory_ids")
                if not isinstance(requested_sub_ids, list):
                    requested_sub_ids = []
                valid_sub_ids = {
                    sub_id
                    for sub_id in requested_sub_ids
                    if sub_id in subcategories
                }
                if (
                    scope_name == "subcategory"
                    and not requested_sub_ids
                    and scoped_subcategories
                ):
                    valid_sub_ids.add(scoped_subcategories[0]["id"])
                if valid_sub_ids or not subcategories:
                    candidate["category_ids"].add(category["id"])
                    candidate["subcategories"].update(
                        subcategories[sub_id]["name"] for sub_id in valid_sub_ids
                    )

    log.info("Discovered %s distinct brand candidates", len(candidates))
    new_count = 0
    for candidate in candidates.values():
        name = candidate["name"]
        if norm(name) in existing_names:
            report["skipped_existing"].append(name)
            continue
        if not candidate["category_ids"]:
            report["rejected"].append({"brand": name, "why": "no valid category/subcategory match"})
            continue
        if args.limit is not None and new_count >= args.limit:
            break
        log.info("Building and checking brand: %s", name)
        try:
            details = build_brand(name, sorted(candidate["subcategories"]))
            errors = validate_details(name, details)
            if errors:
                report["rejected"].append({"brand": name, "why": errors})
                log.warning("  rejected by data validation: %s", errors)
                continue
            verified, reason = verify_brand(name, details)
            if not verified:
                report["rejected"].append(
                    {"brand": name, "why": f"not verified: {reason}"}
                )
                continue

            obj = assemble(name, sorted(candidate["category_ids"]), details)
            if args.dry_run:
                log.info("  dry-run would create %s", name)
            else:
                created = directus("POST", "/items/brands", json=obj)
                log.info("  created %s (%s)", name, (created or {}).get("id"))
            report["created"].append(obj)
            existing_names.add(norm(name))
            new_count += 1
            time.sleep(args.sleep)
        except Exception as error:
            log.exception("Brand failed: %s", name)
            report["errors"].append({"brand": name, "error": str(error)})

    output = f"seed_brands_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    log.info(
        "Done. created=%s existing=%s rejected=%s errors=%s -> %s",
        len(report["created"]),
        len(report["skipped_existing"]),
        len(report["rejected"]),
        len(report["errors"]),
        output,
    )


if __name__ == "__main__":
    main()