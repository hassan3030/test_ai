#!/usr/bin/env python3
"""Deduplicate and AI-validate brand records in a local Directus JSON export.

Usage:
    Set OPENAI_API_KEY and DIRECTUS_TOKEN in the environment or .env file.
  python seed_brands_validation.py --dry-run
  python seed_brands_validation.py
"""
import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from urllib.parse import quote, urlparse

import requests

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://dev-dashboard.swibba.com").rstrip("/")
DIRECTUS_TOKEN = (os.getenv("DIRECTUS_TOKEN") or "").replace("Bearer ", "").strip()
FACT_FIELDS = ("name", "description", "website", "country", "year_founded")
REQUIRED_FIELDS = ("name", "description", "website", "country", "year_founded")
LANGS = ("en-US", "ar-SA", "fr-FR", "es-ES", "it-IT", "hi-IN", "ru-RU")
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
SCRIPT_PATTERNS = {
    "ar-SA": re.compile(r"[\u0600-\u06FF]"),
    "hi-IN": re.compile(r"[\u0900-\u097F]"),
    "ru-RU": re.compile(r"[\u0400-\u04FF]"),
}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_brands_validation")
SESSION = requests.Session()


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
            log.warning("AI validation attempt %s/%s failed: %s", attempt, retries, error)
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"AI validation failed: {last_error}")


def directus_request(method, collection, item_id=None, payload=None):
    path = f"/items/{quote(collection, safe='')}"
    if item_id is not None:
        path += f"/{quote(str(item_id), safe='')}"
    response = SESSION.request(
        method,
        f"{DIRECTUS_URL}{path}",
        headers={
            "Authorization": f"Bearer {DIRECTUS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Directus {method} {path} -> {response.status_code}: {response.text[:500]}"
        )
    return response.json().get("data")


def norm(name):
    normalized = unicodedata.normalize("NFKC", str(name)).casefold()
    return re.sub(r"[^\w]", "", normalized)


def slugify(text):
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def category_id(relation):
    if isinstance(relation, dict):
        value = relation.get("categories_id", relation)
        return value.get("id") if isinstance(value, dict) else value
    return relation


def merge_categories(first, second):
    merged = []
    seen = set()
    for relation in (first or []) + (second or []):
        key = category_id(relation)
        marker = str(key) if key is not None else json.dumps(relation, sort_keys=True)
        if marker not in seen:
            merged.append(relation)
            seen.add(marker)
    return merged


def merge_duplicate_records(records):
    unique = []
    by_name = {}
    duplicates = []
    for record in records:
        if not isinstance(record, dict):
            log.warning("Ignoring non-object entry in brands data")
            unique.append(record)
            continue
        key = norm(record.get("name", ""))
        if not key:
            unique.append(record)
            continue
        if key not in by_name:
            by_name[key] = record
            unique.append(record)
            continue

        primary = by_name[key]
        duplicates.append(record.get("name", ""))
        for field, value in record.items():
            if field == "categories":
                primary[field] = merge_categories(primary.get(field), value)
            elif field not in primary or primary[field] in (None, "", [], {}):
                primary[field] = value
    return unique, duplicates


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as stream:
        payload = json.load(stream)
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload, payload["data"]
    if isinstance(payload, list):
        return None, payload
    raise ValueError("Brands JSON must be a list or an object containing a data list")


def record_is_complete(record):
    for field in ("name", "description", "website", "country"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    try:
        year = int(record["year_founded"])
    except (TypeError, ValueError):
        return False
    if not (1 <= year <= datetime.now().year):
        return False
    website = urlparse(record["website"])
    if website.scheme not in ("http", "https") or not website.netloc:
        return False
    return True


def infer_locale(translation):
    code = translation.get("languages_code")
    if code in LANGS:
        return code
    text = " ".join(
        str(translation.get(field) or "") for field in ("name", "description")
    )
    for locale, pattern in SCRIPT_PATTERNS.items():
        if pattern.search(text):
            return locale
    return None


def translation_targets(record):
    translations = record.get("translations")
    if not isinstance(translations, list):
        translations = []
    row_locales = {}
    locale_rows = {}

    for index, translation in enumerate(translations):
        if not isinstance(translation, dict):
            continue
        locale = infer_locale(translation)
        if locale and locale not in locale_rows:
            row_locales[index] = locale
            locale_rows[locale] = (index, translation)

    unused_locales = [locale for locale in LANGS if locale not in locale_rows]
    for index, translation in enumerate(translations):
        if not isinstance(translation, dict) or index in row_locales:
            continue
        locale = LANGS[index] if len(translations) == len(LANGS) else None
        if locale not in unused_locales:
            locale = unused_locales[0] if unused_locales else None
        if locale:
            row_locales[index] = locale
            locale_rows[locale] = (index, translation)
            unused_locales.remove(locale)

    targets = []
    for locale in LANGS:
        existing = locale_rows.get(locale)
        translation = existing[1] if existing else {}
        missing = [
            field
            for field in TRANSLATION_FIELDS
            if not isinstance(translation.get(field), str)
            or not translation[field].strip()
        ]
        if missing or not translation.get("slug"):
            targets.append(
                {
                    "languages_code": locale,
                    "missing_fields": missing,
                    "existing_values": {
                        field: translation.get(field)
                        for field in TRANSLATION_FIELDS
                        if isinstance(translation.get(field), str)
                        and translation[field].strip()
                    },
                }
            )
    return translations, row_locales, locale_rows, targets


def validate_with_ai(record):
    system = (
        "You are a careful brand fact-checker. Check each supplied factual field against "
        "reliable known facts about the real-world organization. Never guess or invent "
        "values. If a value cannot be confidently established, do not correct it and do not "
        "mark it verified. Return JSON only."
    )
    facts = {field: record.get(field) for field in FACT_FIELDS}
    translations, _, _, translation_requests = translation_targets(record)
    user = (
        "Validate this one brand record field by field. Confirm only factual corrections "
        "you are confident about. For missing or incorrect facts, include the corrected value "
        "only if you can confidently establish it. Keep the official brand name unchanged "
        "unless it is clearly misspelled. Do not change IDs, status, category links, or other "
        "metadata. Year founded must be an integer. Website must be the official site. "
        "Return verified_fields as the factual fields you checked and can affirm; corrections "
        "must contain only field values you can confidently support. Use confidence from 0 "
        "to 1 for the overall real-brand and data check.\n"
        'Return {"is_real":true,"confidence":0.0,"verified_fields":[],"corrections":{},"translation_fills":[],"reason":""}.\n\n'
        + json.dumps(facts, ensure_ascii=False)
        + "\n\nFill only missing translation fields for these locales. Preserve existing values. "
        "Translate factual company information naturally. You may write concise, accurate "
        "short descriptions, about-us copy, and metadata from the supplied verified facts. "
        "Only provide a tagline, mission, or vision when it is an established official statement; "
        "only provide contact or support details that are publicly listed by the organization. "
        "Never infer email addresses or invent official claims. Leave a field empty when no "
        "trustworthy value is known. Return each requested locale as {languages_code, fields}, "
        "with fields containing only requested field names.\n"
        + json.dumps(translation_requests, ensure_ascii=False)
    )
    return llm_json(system, user)


def merge_translation_fills(record, result):
    translations, row_locales, locale_rows, targets = translation_targets(record)
    if not isinstance(record.get("translations"), list):
        record["translations"] = translations

    locale_updates = set()
    for index, locale in row_locales.items():
        translation = record["translations"][index]
        if translation.get("languages_code") not in LANGS:
            translation["languages_code"] = locale
            locale_updates.add(locale)

    for locale in LANGS:
        if locale not in locale_rows:
            translation = {
                "brands_id": record.get("id"),
                "languages_code": locale,
            }
            record["translations"].append(translation)
            locale_rows[locale] = (len(record["translations"]) - 1, translation)

    fills = result.get("translation_fills", []) if isinstance(result, dict) else []
    fills_by_locale = {
        fill.get("languages_code"): fill.get("fields", {})
        for fill in fills
        if isinstance(fill, dict) and isinstance(fill.get("fields"), dict)
    } if isinstance(fills, list) else {}

    updates = []
    unresolved = []
    for target in targets:
        locale = target["languages_code"]
        translation = locale_rows[locale][1]
        proposed = fills_by_locale.get(locale, {})
        updated_fields = ["languages_code"] if locale in locale_updates else []
        for field in target["missing_fields"]:
            value = proposed.get(field)
            if not isinstance(value, str) or not value.strip():
                unresolved.append({"locale": locale, "field": field})
                continue
            if field in ("name", "description"):
                pattern = SCRIPT_PATTERNS.get(locale)
                if pattern and not pattern.search(value):
                    unresolved.append({"locale": locale, "field": field, "reason": "wrong script"})
                    continue
            if not isinstance(translation.get(field), str) or not translation[field].strip():
                translation[field] = value.strip()
                updated_fields.append(field)

        if not translation.get("slug") and translation.get("name"):
            translation["slug"] = slugify(translation["name"])
            updated_fields.append("slug")
        if updated_fields:
            updates.append({"locale": locale, "fields": updated_fields})

    return updates, unresolved


def update_directus_translations(record, updates, collection, dry_run=False):
    _, _, locale_rows, _ = translation_targets(record)
    results = []
    for update in updates:
        locale = update["locale"]
        translation = locale_rows[locale][1]
        changed_fields = update["fields"]
        payload = {
            field: translation[field]
            for field in changed_fields
            if field in TRANSLATION_FIELDS or field in ("slug", "languages_code")
        }
        payload.setdefault("languages_code", locale)
        if dry_run:
            results.append(
                {"locale": locale, "fields": sorted(payload), "status": "dry_run"}
            )
            continue

        translation_id = translation.get("id")
        if translation_id is not None:
            directus_request("PATCH", collection, translation_id, payload)
            status = "updated"
        else:
            brand_id = translation.get("brands_id") or record.get("id")
            if not brand_id:
                raise ValueError(f"Cannot create {locale} translation without a brand id")
            payload["brands_id"] = brand_id
            created = directus_request("POST", collection, payload=payload)
            if isinstance(created, dict) and created.get("id") is not None:
                translation["id"] = created["id"]
            translation["brands_id"] = brand_id
            status = "created"
        results.append(
            {"locale": locale, "fields": sorted(payload), "status": status}
        )
    return results


def validate_corrections(result):
    if not isinstance(result, dict):
        return {}, []
    corrections = result.get("corrections")
    verified = result.get("verified_fields")
    if not isinstance(corrections, dict):
        corrections = {}
    if not isinstance(verified, list):
        verified = []
    valid = {}
    issues = []
    for field, value in corrections.items():
        if field not in FACT_FIELDS:
            issues.append(f"ignored unsupported field: {field}")
            continue
        if field not in verified:
            issues.append(f"ignored unverified correction: {field}")
            continue
        if field == "year_founded":
            try:
                value = int(value)
                if not (1 <= value <= datetime.now().year):
                    raise ValueError
            except (TypeError, ValueError):
                issues.append("ignored invalid year_founded correction")
                continue
        elif not isinstance(value, str) or not value.strip():
            issues.append(f"ignored empty or invalid correction: {field}")
            continue
        elif field == "website":
            parsed = urlparse(value.strip())
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                issues.append("ignored invalid website correction")
                continue
            value = value.strip()
        else:
            value = value.strip()
        valid[field] = value
    return valid, issues


def write_json_atomic(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, delete=False
        ) as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            temp_path = stream.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def main():
    global OPENAI_MODEL
    parser = argparse.ArgumentParser(
        description="Deduplicate and validate brands in a local JSON export"
    )
    parser.add_argument(
        "--brands-file",
        default=os.path.join(os.path.dirname(__file__), "brands_validation.json"),
        help="local brands JSON file to validate and update",
    )
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    parser.add_argument(
        "--directus-collection",
        default="brands_translations",
        help="Directus translation collection (default: brands_translations)",
    )
    parser.add_argument("--limit", type=int, help="maximum number of brands sent for AI validation")
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--model", help=f"AI model to use (default: {OPENAI_MODEL})")
    args = parser.parse_args()
    if args.model:
        OPENAI_MODEL = args.model
    if not OPENAI_API_KEY:
        sys.exit("Set OPENAI_API_KEY in the environment or .env file.")
    if not args.dry_run and not DIRECTUS_TOKEN:
        sys.exit("Set DIRECTUS_TOKEN in the environment or .env file, or use --dry-run.")

    try:
        root, records = load_json(args.brands_file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        sys.exit(f"Could not load brands file: {error}")

    unique_records, duplicate_names = merge_duplicate_records(records)
    report = {
        "validated": [],
        "skipped_complete": [],
        "updated": [],
        "translations_updated": [],
        "directus_translation_updates": [],
        "translation_fields_unfilled": [],
        "unverified": [],
        "errors": [],
        "duplicates_removed": duplicate_names,
    }
    processed = 0
    for index, record in enumerate(unique_records, 1):
        if not isinstance(record, dict):
            continue
        name = record.get("name") or f"record-{index}"
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1
        log.info("Validating brand %s/%s: %s", processed, len(unique_records), name)
        try:
            result = validate_with_ai(record)
            confidence = float(result.get("confidence", 0))
            if result.get("is_real") is not True or confidence < 0.8:
                reason = result.get("reason", "brand not confirmed with sufficient confidence")
                report["unverified"].append({"name": name, "reason": reason})
                continue

            translation_updates, translation_unfilled = merge_translation_fills(record, result)
            if translation_updates:
                report["translations_updated"].append(
                    {"name": name, "locales": translation_updates}
                )
                directus_updates = update_directus_translations(
                    record,
                    translation_updates,
                    args.directus_collection,
                    dry_run=args.dry_run,
                )
                report["directus_translation_updates"].append(
                    {"name": name, "locales": directus_updates}
                )
            if translation_unfilled:
                report["translation_fields_unfilled"].append(
                    {"name": name, "fields": translation_unfilled}
                )

            corrections, issues = validate_corrections(result)
            if issues:
                report["errors"].append({"name": name, "issues": issues})
            verified_fields = result.get("verified_fields", [])
            if not isinstance(verified_fields, list):
                verified_fields = []
            verified_fields = set(verified_fields)
            unresolved_facts = [
                field
                for field in FACT_FIELDS
                if field not in verified_fields and field not in corrections
            ]
            candidate_record = {**record, **corrections}
            if "slug" in record and candidate_record.get("name"):
                candidate_record["slug"] = slugify(candidate_record["name"])
            if unresolved_facts or not record_is_complete(candidate_record):
                missing = [
                    field
                    for field in REQUIRED_FIELDS
                    if candidate_record.get(field) in (None, "", [])
                ]
                report["unverified"].append(
                    {
                        "name": name,
                        "reason": "not all factual fields were verified or required data is incomplete",
                        "fields": sorted(set(unresolved_facts + missing)),
                    }
                )
                continue

            report["validated"].append(name)
            slug_changed = (
                "slug" in record and record.get("slug") != candidate_record.get("slug")
            )
            if corrections or slug_changed:
                changed_fields = dict(corrections)
                if slug_changed:
                    changed_fields["slug"] = candidate_record["slug"]
                before = {field: record.get(field) for field in changed_fields}
                record.update(changed_fields)
                report["updated"].append(
                    {"name": name, "before": before, "after": changed_fields}
                )
            else:
                report["skipped_complete"].append(name)
            log.info("  verified with confidence %.2f", confidence)
        except Exception as error:
            log.exception("Validation failed for %s", name)
            report["errors"].append({"name": name, "error": str(error)})
        if args.sleep > 0:
            time.sleep(args.sleep)

    if root is None:
        output_payload = unique_records
    else:
        root["data"] = unique_records
        output_payload = root
    if not args.dry_run:
        write_json_atomic(args.brands_file, output_payload)

    report_path = os.path.join(
        os.path.dirname(os.path.abspath(args.brands_file)),
        f"seed_brands_validation_report_{datetime.now():%Y%m%d_%H%M%S}.json",
    )
    write_json_atomic(report_path, report)
    log.info(
        "Done. validated=%s skipped=%s updated=%s translation_rows_updated=%s unverified=%s duplicates=%s; %s",
        len(report["validated"]),
        len(report["skipped_complete"]),
        len(report["updated"]),
        len(report["translations_updated"]),
        len(report["unverified"]),
        len(report["duplicates_removed"]),
        "dry run; brands file unchanged" if args.dry_run else f"updated {args.brands_file}",
    )
    log.info("Report: %s", report_path)


if __name__ == "__main__":
    main()