#!/usr/bin/env python3
"""Discover, verify, and seed real product models for every input series.

Usage:
    python seed_models.py --dry-run --limit 2
    python seed_models.py --limit 2
    python seed_models.py --series-id <series-uuid> --dry-run
    # If interrupted, rerun the same command to resume from the last unfinished series.
"""
import argparse
import json
import logging
import math
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime
from urllib.parse import urlparse

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
DIRECTUS_TOKEN = (os.getenv("DIRECTUS_TOKEN") or "").replace("Bearer ", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

LANGS = ["en-US", "ar-SA", "fr-FR", "es-ES", "it-IT", "hi-IN", "ru-RU"]
SCRIPT_CHECK = {  # script each translation must be written in (None = latin, no check)
    "ar-SA": re.compile(r"[\u0600-\u06FF]"),
    "hi-IN": re.compile(r"[\u0900-\u097F]"),
    "ru-RU": re.compile(r"[\u0400-\u04FF]"),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_models")


# --------------------------------------------------------------------------- http
def make_session():
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}))
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


def model_name_norm(name):
    text = unicodedata.normalize("NFKC", str(name)).lower().replace("+", " plus ")
    return re.sub(r"[^\w]", "", text, flags=re.UNICODE)


def model_slugify(name):
    return slugify(str(name).replace("+", " plus "))


def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def relation_id(value):
    return value.get("id") if isinstance(value, dict) else value


def relation_context(value, by_id, by_name):
    relation = value if isinstance(value, dict) else {}
    raw_id = relation_id(value)
    name = relation.get("name")
    record = by_id.get(str(raw_id)) if raw_id is not None else None
    if record is None and name:
        record = by_name.get(norm(name))
    if record is None and isinstance(value, str):
        record = by_name.get(norm(value))
        if record:
            name = record.get("name")
    return {
        "id": (record or {}).get("id", raw_id),
        "name": (record or {}).get("name", name),
    }


def load_relation_indexes():
    brands = dget("brands", {"fields": "id,name,slug"})
    subcategories = dget("subcategories", {"fields": "id,name,slug"})
    brand_by_id = {str(item["id"]): item for item in brands if item.get("id")}
    subcategory_by_id = {str(item["id"]): item for item in subcategories if item.get("id")}
    brand_by_name = {norm(item.get("name")): item for item in brands if item.get("name")}
    subcategory_by_name = {
        norm(item.get("name")): item for item in subcategories if item.get("name")
    }
    return brand_by_id, brand_by_name, subcategory_by_id, subcategory_by_name


# --------------------------------------------------------------------------- step 1: discover model names
DISCOVER_SYSTEM = (
    "You are a meticulous product-catalog researcher. Distinguish the hierarchy: a SERIES is the umbrella "
    "product family; MODELS are its individual officially named sellable products/variants. Enumerate every "
    "real model for the supplied series, not just the family name. For example, Samsung series Galaxy S23 "
    "has models Galaxy S23, Galaxy S23+, and Galaxy S23 Ultra; Samsung series Galaxy S24 has models Galaxy "
    "S24, Galaxy S24+, and Galaxy S24 Ultra. The base model may have the same name as its series and must "
    "still be included. Do not merge sibling models into one entry. Never invent a SKU, or list colors/sizes "
    "as separate models unless they are official distinct model variants. If no model can be substantiated, "
    "return an empty list. Reply with JSON only."
)
 
BUILD_SYSTEM = (
    "You are a careful product researcher. Use only specific, reliable source-backed facts about the real model. "
    "Never guess or fabricate values, release dates, or source URLs. If a required fact cannot be supported, "
    "return null for it; the caller will reject incomplete records. Never omit a known applicable attribute. "
    "Reply with JSON only."
)

VERIFY_SYSTEM = (
    "You are an independent, conservative product-catalog fact checker. Assess whether the named product model "
    "really exists and belongs to the stated brand and series, and whether its price and release-date claims "
    "are supported by the supplied source URLs. Reject unsupported, mismatched, or invented models or values. "
    "Do not treat the candidate description or a URL by itself as proof. Reply with JSON only."
)


def series_context(series, brand, subcategory):
    return {
        "series_id": series.get("id"),
        "series_name": series.get("name"),
        "release_year": series.get("release_year"),
        "description": series.get("description"),
        "brand_id": brand.get("id"),
        "brand_name": brand.get("name"),
        "subcategory_id": subcategory.get("id"),
        "subcategory_name": subcategory.get("name"),
    }


def discover_models(context):
    initial_user = (
        "Enumerate every distinct, officially named model in this exact series. Follow the series-versus-model "
        "hierarchy in your system instructions. Include the base model even when its official name exactly "
        "matches the series name, plus every separately named sibling model; never substitute the parent-series "
        "name for its full model list. Include official generations and named powertrain/body configurations when "
        "they are sold as distinct models. Treat release_year as a clue, not a reason to omit the series when null. "
        "Do not include generic categories, colors, sizes, or invented configurations. Include model number and "
        "model release year only when known; otherwise use null. Return {\"models\":[{\"name\":\"\","
        "\"model_number\":null,\"release_year\":null}]}.\n\n"
        + json.dumps(context, ensure_ascii=False)
    )
    first = llm_json(DISCOVER_SYSTEM, initial_user)
    models = first.get("models") if isinstance(first, dict) else None
    collected = [item for item in models if isinstance(item, dict)] if isinstance(models, list) else []

    audit_user = (
        "Completeness audit: independently review the series and your prior list below. Return any real, "
        "official sibling/base models that were omitted, including common named tiers such as Plus, Ultra, Pro, "
        "Max, FE, GT, or officially distinct body/powertrain versions when applicable. Do not repeat a model "
        "already listed, do not split colors/sizes into models, and do not invent variants. If the first pass "
        "already contains every known model, return an empty models list. Use the same JSON schema.\n\n"
        + json.dumps({"series_context": context, "already_found": collected}, ensure_ascii=False)
    )
    audit = llm_json(DISCOVER_SYSTEM, audit_user)
    additional = audit.get("models") if isinstance(audit, dict) else None
    if isinstance(additional, list):
        by_name = {model_name_norm(item.get("name", "")): item for item in collected if item.get("name")}
        for item in additional:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            key = model_name_norm(item["name"])
            existing = by_name.get(key)
            if existing:
                for field in ("model_number", "release_year"):
                    if existing.get(field) in (None, "") and item.get(field) not in (None, ""):
                        existing[field] = item[field]
            else:
                collected.append(item)
                by_name[key] = item
    return collected


def build_model(context, candidate, validation_feedback=None):
    user = (
        "Build one model record for this candidate. Produce a factual, specific description and official "
        "model number if known. REQUIRED REAL-WORLD FIELDS: base_price is the current official US price in USD "
        "for this exact base model; msrp is its official US launch MSRP in USD; release_date is its exact US "
        "first-on-sale date in YYYY-MM-DD. Do not substitute an estimated, foreign-market, third-party used, "
        "or sibling-model value. Find a direct HTTPS source URL for each of these three fields, preferably the "
        "manufacturer's US product page or official US newsroom/price announcement. If a value or source cannot "
        "be substantiated, return null/empty and the caller will reject this candidate rather than guess. Include "
        "factual technical "
        "attributes. For attribute_values, include the maximum number of distinct, model-specific facts you "
        "can support; do not stop at only the headline specs. Add one entry per property with a concise "
        "property label in value and its exact known specification in available_options. Depending on the "
        "product, inspect relevant properties such as materials, construction, dimensions, weight, components, "
        "performance, capacity, compatibility, connectivity, power, battery, display, camera, processor, "
        "storage, included features, fit, and care. Use only properties applicable to this category and model; "
        "avoid duplicates, vague filler, and unsupported claims. Do not treat colors or sizes as separate "
        "attributes unless they are official model distinctions. Translate name and description into these "
        "locales: " + ", ".join(LANGS) + ".\n"
        "Keep official brand/product names in Latin script where customary; use Arabic, Devanagari, and "
        "Cyrillic for ar-SA, hi-IN, and ru-RU respectively. Attribute entries must use value and "
        "available_options; set attribute_definitions_id and is_variant to null. Return every substantiated "
        "attribute, not a fixed short sample.\n"
        "Return this JSON shape: {\"description\":\"\",\"model_number\":null,\"base_price\":null,"
        "\"msrp\":null,\"release_date\":null,\"field_sources\":{\"base_price\":\"https://...\","
        "\"msrp\":\"https://...\",\"release_date\":\"https://...\"},"
        "\"year_start\":null,\"year_end\":null,"
        "\"translations\":[{\"languages_code\":\"en-US\",\"name\":\"\",\"description\":\"\"}],"
        "\"attribute_values\":[{\"value\":\"\",\"available_options\":\"\"}]}\n\n"
          + json.dumps({"series_context": context, "candidate": candidate}, ensure_ascii=False)
          + ("\n\nCorrect these validation errors in the new response: "
              + json.dumps(validation_feedback, ensure_ascii=False) if validation_feedback else "")
    )
    data = llm_json(BUILD_SYSTEM, user)
    if not isinstance(data, dict):
        raise ValueError("model details response was not an object")
    return data


def optional_year(value):
    if value in (None, ""):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return value
    return year if 1000 <= year <= datetime.now().year + 1 else value


def optional_price(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return value
    return price if math.isfinite(price) and price >= 0 else value


def assemble_model(series, candidate, details):
    name = str(candidate.get("name") or "").strip()
    by_code = {
        item.get("languages_code"): item
        for item in details.get("translations", [])
        if isinstance(item, dict)
    }
    translations = []
    for code in LANGS:
        item = by_code.get(code, {})
        translated_name = str(item.get("name") or "").strip()
        translated_description = str(item.get("description") or "").strip()
        translations.append({
            "languages_code": code,
            "name": translated_name,
            "description": translated_description,
            "slug": slugify(translated_name),
        })

    attributes = []
    for item in details.get("attribute_values", []):
        if not isinstance(item, dict):
            continue
        attributes.append({
            "attribute_definitions_id": None,
            "value": str(item.get("value") or "").strip(),
            "available_options": str(item.get("available_options") or "").strip(),
            "is_variant": None,
        })

    return {
        "status": "active",
        "series_id": series.get("id"),
        "name": name,
        "slug": slugify(name),
        "model_number": details.get("model_number") or candidate.get("model_number"),
        "description": str(details.get("description") or "").strip(),
        "base_price": optional_price(details.get("base_price")),
        "msrp": optional_price(details.get("msrp")),
        "release_date": details.get("release_date") or None,
        "year_start": optional_year(details.get("year_start") or candidate.get("release_year")),
        "year_end": optional_year(details.get("year_end") or candidate.get("release_year")),
        "translations": translations,
        "attribute_values": attributes,
    }


def validate_model(obj, series, field_sources=None):
    errors = []
    for field in ("series_id", "name", "slug", "description", "translations"):
        if obj.get(field) in (None, "", []):
            errors.append(f"missing {field}")
    if errors:
        return errors
    if str(obj["series_id"]) != str(series.get("id")):
        errors.append("model series_id does not match input series")
    if len(obj["description"]) < 30:
        errors.append("description too short or not factual enough")
    if obj["model_number"] is not None and not isinstance(obj["model_number"], str):
        errors.append("model_number must be a string or null")
    for field in ("base_price", "msrp"):
        value = obj.get(field)
        if value is None:
            errors.append(f"{field} is required with a real US-market USD value")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            errors.append(f"{field} must be a finite positive USD amount")
    for field in ("year_start", "year_end"):
        if obj[field] is not None:
            if not isinstance(obj[field], int) or not 1000 <= obj[field] <= datetime.now().year + 1:
                errors.append(f"{field} must be a valid year or null")
    if obj["year_start"] and obj["year_end"] and obj["year_start"] > obj["year_end"]:
        errors.append("year_start is after year_end")
    if not obj.get("release_date"):
        errors.append("release_date is required as the exact US first-on-sale date")
    else:
        try:
            date.fromisoformat(obj["release_date"])
        except (TypeError, ValueError):
            errors.append("release_date must be an exact ISO date (YYYY-MM-DD)")

    field_sources = field_sources if isinstance(field_sources, dict) else {}
    for field in ("base_price", "msrp", "release_date"):
        source = field_sources.get(field)
        parsed = urlparse(source) if isinstance(source, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{field} requires an HTTPS source URL")

    codes = [item.get("languages_code") for item in obj["translations"] if isinstance(item, dict)]
    if sorted(codes) != sorted(LANGS):
        errors.append(f"translations must contain each locale exactly once: {LANGS}")
    for item in obj["translations"]:
        if not isinstance(item, dict):
            errors.append("translation entry must be an object")
            continue
        code = item.get("languages_code")
        if not item.get("name") or not item.get("description") or not item.get("slug"):
            errors.append(f"{code}: empty translated name/description/slug")
            continue
        script = SCRIPT_CHECK.get(code)
        if script and not (script.search(item["name"]) and script.search(item["description"])):
            errors.append(f"{code}: text not written in expected script")
        if code == "en-US" and norm(item["name"]) != norm(obj["name"]):
            errors.append("en-US name differs from model name")

    for item in obj["attribute_values"]:
        if not item.get("value") or not item.get("available_options"):
            errors.append("attribute value/options are empty")
    return errors


def verify_real_model(context, obj, field_sources):
    user = (
        "Independently determine whether this is a real, officially named product model from the stated "
        "brand and exact series. Also verify that base_price is the current official US price in USD, msrp is "
        "the official US launch MSRP in USD, and release_date is the exact US first-on-sale date, using each "
        "provided source URL. Do not claim verification based on model memory alone or an unrelated URL. "
        "Return {\"exists\":true,\"field_values_supported\":true,\"confidence\":0.0,\"reason\":\"\"}.\n\n"
        + json.dumps({"series_context": context, "candidate_model": obj, "field_sources": field_sources}, ensure_ascii=False)
    )
    try:
        result = llm_json(VERIFY_SYSTEM, user, retries=2)
        accepted = (
            bool(result.get("exists"))
            and bool(result.get("field_values_supported"))
            and float(result.get("confidence", 0)) >= 0.8
        )
        return accepted, str(result.get("reason") or ""), float(result.get("confidence", 0))
    except Exception as error:  # noqa
        return False, f"verification failed: {error}", 0.0


# --------------------------------------------------------------------------- main loop
def unique_slug(name, series_id, brand_name, used_slugs):
    base = model_slugify(name) or "model"
    slug = base
    if slug in used_slugs:
        owner = slugify(brand_name) or str(series_id)[:8]
        slug = f"{base}-{owner}"
    index = 2
    while slug in used_slugs:
        slug = f"{base}-{index}"
        index += 1
    return slug


def model_duplicate(obj, series_id, names_by_series, numbers_by_series):
    key = str(series_id)
    name_key = model_name_norm(obj.get("name", ""))
    raw_number = obj.get("model_number")
    number_key = norm(raw_number) if raw_number else ""
    return name_key in names_by_series.get(key, set()) or bool(
        number_key and number_key in numbers_by_series.get(key, set())
    )


def record_model_key(obj, series_id, names_by_series, numbers_by_series):
    key = str(series_id)
    names_by_series.setdefault(key, set()).add(model_name_norm(obj.get("name", "")))
    raw_number = obj.get("model_number")
    number = norm(raw_number) if raw_number else ""
    if number:
        numbers_by_series.setdefault(key, set()).add(number)


def find_existing_model(candidate, series_id, models_by_series):
    series_models = models_by_series.get(str(series_id), [])
    candidate_name = model_name_norm(candidate.get("name", ""))
    candidate_number = norm(candidate.get("model_number", "")) if candidate.get("model_number") else ""
    for existing in series_models:
        if model_name_norm(existing.get("name", "")) == candidate_name:
            return existing
        existing_number = norm(existing.get("model_number", "")) if existing.get("model_number") else ""
        if candidate_number and existing_number == candidate_number:
            return existing
    return None


def save_report(report, path):
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)


def new_report(checkpoint):
    return {
        "state": "running",
        "checkpoint": checkpoint,
        "created": [],
        "updated": [],
        "would_create": [],
        "would_update": [],
        "skipped_existing": [],
        "rejected": [],
        "errors": [],
        "series": [],
    }


def main():
    global OPENAI_MODEL
    ap = argparse.ArgumentParser(description="Discover and seed verified models for every series in a JSON export.")
    ap.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "cataloge content", "series_seed_models.json"))
    ap.add_argument("--dry-run", action="store_true", help="discover and verify models without POSTing")
    ap.add_argument("--series-id", action="append", help="process only this series ID (repeatable)")
    ap.add_argument("--start", type=int, default=0, help="start at this zero-based series index")
    ap.add_argument("--limit", type=int, help="maximum number of series to process")
    ap.add_argument(
        "--report",
        help="report/checkpoint JSON path (reused to resume an interrupted run)",
    )
    ap.add_argument("--sleep", type=float, default=0.5, help="delay between model records")
    ap.add_argument("--model", help=f"OpenAI model to use (default: {OPENAI_MODEL})")
    args = ap.parse_args()

    if args.model:
        OPENAI_MODEL = args.model
    if not DIRECTUS_TOKEN or not OPENAI_API_KEY:
        ap.error("Set DIRECTUS_TOKEN and OPENAI_API_KEY in the environment or .env file")
    try:
        with open(args.file, "r", encoding="utf-8-sig") as stream:
            source = json.load(stream)
        series_rows = source.get("data", []) if isinstance(source, dict) else source
        if not isinstance(series_rows, list):
            raise ValueError("series input must be a list or an object containing a data list")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        ap.error(str(error))

    if args.series_id:
        requested = {str(value) for value in args.series_id}
        series_rows = [row for row in series_rows if str(row.get("id")) in requested]
    series_rows = series_rows[args.start:]
    if args.limit is not None:
        series_rows = series_rows[:max(args.limit, 0)]

    log.info("Loaded %s input series from %s", len(series_rows), args.file)
    checkpoint = {
        "file": os.path.abspath(args.file),
        "series_ids": [
            str(row.get("id")) if isinstance(row, dict) else None for row in series_rows
        ],
    }
    output = args.report or os.path.join(os.path.dirname(__file__), "seed_models_report.json")
    report = new_report(checkpoint)
    if os.path.exists(output):
        try:
            with open(output, "r", encoding="utf-8") as stream:
                previous_report = json.load(stream)
        except (OSError, ValueError) as error:
            ap.error(f"cannot read existing report/checkpoint {output}: {error}")
        if isinstance(previous_report, dict) and previous_report.get("state") == "running":
            if previous_report.get("checkpoint") != checkpoint:
                ap.error(
                    f"existing checkpoint {output} belongs to a different input or series selection; "
                    "use --report with a different path or restore the matching selection"
                )
            report = previous_report

    completed_statuses = {"processed", "no_models_returned", "invalid_source"}
    completed_count = 0
    prior_series = report.get("series", [])
    if not isinstance(prior_series, list):
        ap.error(f"existing checkpoint {output} has an invalid series list")
    while completed_count < min(len(prior_series), len(series_rows)):
        previous = prior_series[completed_count]
        expected_id = checkpoint["series_ids"][completed_count]
        if (
            not isinstance(previous, dict)
            or (
                str(previous.get("series_id")) if previous.get("series_id") is not None else None
            ) != expected_id
            or previous.get("status") not in completed_statuses
        ):
            break
        completed_count += 1

    if completed_count < len(prior_series):
        retry_ids = {
            str(item.get("series_id"))
            for item in prior_series[completed_count:]
            if isinstance(item, dict) and item.get("series_id") is not None
        }
        report["series"] = prior_series[:completed_count]
        for field in (
            "created",
            "updated",
            "would_create",
            "would_update",
            "skipped_existing",
            "rejected",
            "errors",
        ):
            report[field] = [
                item for item in report.get(field, [])
                if not isinstance(item, dict) or str(item.get("series_id")) not in retry_ids
            ]
    series_rows = series_rows[completed_count:]
    if completed_count:
        log.info("Resuming after %s completed series", completed_count)

    brand_by_id, brand_by_name, sub_by_id, sub_by_name = load_relation_indexes()
    existing_models = dget("models", {"fields": "id,name,slug,model_number,series_id,base_price,msrp,release_date"})
    names_by_series = {}
    numbers_by_series = {}
    models_by_series = {}
    used_slugs = set()
    for model in existing_models:
        series_id = relation_id(model.get("series_id"))
        if series_id is not None:
            record_model_key(model, series_id, names_by_series, numbers_by_series)
            models_by_series.setdefault(str(series_id), []).append(model)
        if model.get("slug"):
            used_slugs.add(model["slug"])

    report["state"] = "running"
    save_report(report, output)
    for index, series in enumerate(series_rows, 1):
        series_id = series.get("id") if isinstance(series, dict) else None
        series_name = (series.get("name") or "") if isinstance(series, dict) else ""
        result = {
            "series_id": series_id,
            "series_name": series_name,
            "release_year": series.get("release_year") if isinstance(series, dict) else None,
            "models_found": 0,
            "models_discovered": [],
            "status": "pending",
            "created": [],
            "updated": [],
            "would_create": [],
            "would_update": [],
            "skipped_existing": [],
            "rejected": [],
            "errors": [],
        }
        report["series"].append(result)
        log.info("[%s/%s] Series: %s (%s)", index, len(series_rows), series_name, series_id)
        try:
            if not series_id or not series_name:
                result["status"] = "invalid_source"
                result["errors"].append("series is missing id or name")
                log.error("  rejected source row: missing series id or name")
                continue

            brand = relation_context(series.get("brand_id"), brand_by_id, brand_by_name)
            subcategory = relation_context(series.get("subcategory_id"), sub_by_id, sub_by_name)
            context = series_context(series, brand, subcategory)
            candidates = discover_models(context)
            result["models_found"] = len(candidates)
            log.info("  discovery returned %s model candidates", len(candidates))
            result["models_discovered"] = [
                str(candidate["name"]).strip()
                for candidate in candidates
                if isinstance(candidate, dict) and str(candidate.get("name") or "").strip()
            ]
            for model_name in result["models_discovered"]:
                log.info("  AI discovered model: %s", model_name)
            if not candidates:
                result["status"] = "no_models_returned"
                log.warning("  no candidates returned; series recorded for follow-up")
                continue

            seen_names = set()
            seen_numbers = set()
            for candidate in candidates:
                if not isinstance(candidate, dict) or not str(candidate.get("name") or "").strip():
                    rejection = {"candidate": candidate, "why": "missing model name"}
                    result["rejected"].append(rejection)
                    report["rejected"].append({"series_id": series_id, **rejection})
                    log.warning("  rejected candidate with missing model name")
                    continue
                candidate_name = str(candidate["name"]).strip()
                candidate_number = str(candidate.get("model_number") or "").strip()
                if model_name_norm(candidate_name) in seen_names or (candidate_number and norm(candidate_number) in seen_numbers):
                    skipped = {"model": candidate_name, "why": "duplicate in AI results"}
                    result["skipped_existing"].append(skipped)
                    report["skipped_existing"].append({"series_id": series_id, **skipped})
                    log.info("  skipped duplicate candidate: %s", candidate_name)
                    continue
                seen_names.add(model_name_norm(candidate_name))
                if candidate_number:
                    seen_numbers.add(norm(candidate_number))
                existing_model = find_existing_model(candidate, series_id, models_by_series)
                if existing_model or model_duplicate(candidate, series_id, names_by_series, numbers_by_series):
                    skipped = {"model": candidate_name, "why": "name or model_number already exists"}
                    result["skipped_existing"].append(skipped)
                    report["skipped_existing"].append({"series_id": series_id, **skipped})
                    log.info("  skipped existing model before building details: %s", candidate_name)
                    continue

                try:
                    errors = []
                    for attempt in range(1, 4):
                        details = build_model(context, candidate, validation_feedback=errors or None)
                        model = assemble_model(series, candidate, details)
                        field_sources = details.get("field_sources")
                        errors = validate_model(model, series, field_sources)
                        if not errors:
                            break
                        log.warning("  validation attempt %s/3 for %s failed: %s", attempt, candidate_name, errors)
                    if errors:
                        rejection = {"model": candidate_name, "why": errors}
                        result["rejected"].append(rejection)
                        report["rejected"].append({"series_id": series_id, **rejection})
                        log.warning("  rejected after three validation attempts: %s", candidate_name)
                        continue

                    if model_duplicate(model, series_id, names_by_series, numbers_by_series):
                        skipped = {"model": candidate_name, "why": "name or model_number already exists"}
                        result["skipped_existing"].append(skipped)
                        report["skipped_existing"].append({"series_id": series_id, **skipped})
                        log.info("  skipped existing model: %s", candidate_name)
                        continue

                    verified, reason, confidence = verify_real_model(context, model, field_sources)
                    if not verified:
                        rejection = {
                            "model": candidate_name,
                            "why": "not independently verified",
                            "confidence": confidence,
                            "reason": reason,
                        }
                        result["rejected"].append(rejection)
                        report["rejected"].append({"series_id": series_id, **rejection})
                        log.warning("  verification rejected %s (confidence %.2f): %s", candidate_name, confidence, reason)
                        continue

                    model["slug"] = unique_slug(model["name"], series_id, brand.get("name"), used_slugs)
                    model["translations"][0]["slug"] = model["slug"]
                    if args.dry_run:
                        report["would_create"].append({**model, "field_sources": field_sources})
                        result["would_create"].append(model["name"])
                        log.info("  ~ dry-run would create model: %s", model["name"])
                    else:
                        created = directus("POST", "/items/models", json=model)
                        report["created"].append({"id": (created or {}).get("id"), **model, "field_sources": field_sources})
                        result["created"].append(model["name"])
                        log.info("  + created model: %s (%s)", model["name"], (created or {}).get("id"))
                    used_slugs.add(model["slug"])
                    record_model_key(model, series_id, names_by_series, numbers_by_series)
                    time.sleep(args.sleep)
                except Exception as error:  # noqa
                    issue = {"model": candidate_name, "error": str(error)}
                    result["errors"].append(issue)
                    report["errors"].append({"series_id": series_id, "series": series_name, **issue})
                    log.exception("  model failed: %s", candidate_name)
            result["status"] = "processed"
            log.info(
                "  series outcome: candidates=%s created=%s updated=%s dry_run_create=%s dry_run_update=%s skipped=%s rejected=%s errors=%s",
                result["models_found"], len(result["created"]), len(result["updated"]),
                len(result["would_create"]), len(result["would_update"]),
                len(result["skipped_existing"]), len(result["rejected"]), len(result["errors"]),
            )
        except Exception as error:  # noqa
            result["status"] = "error"
            result["errors"].append(str(error))
            report["errors"].append({"series_id": series_id, "series": series_name, "error": str(error)})
            log.exception("  series failed: %s", series_name)
        finally:
            save_report(report, output)

    report["state"] = "complete"
    save_report(report, output)
    log.info("Done. created=%s updated=%s dry_run_create=%s dry_run_update=%s skipped=%s rejected=%s errors=%s -> %s",
             len(report["created"]), len(report["updated"]), len(report["would_create"]),
             len(report["would_update"]), len(report["skipped_existing"]),
             len(report["rejected"]), len(report["errors"]), output)


if __name__ == "__main__":
    main()