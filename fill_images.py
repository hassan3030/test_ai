#!/usr/bin/env python3
"""
Fill the "image" field of each product in images3.json using the Wikipedia API.

Every URL written is read from a live API response (pageimages -> original),
so nothing is guessed or built from memory. Items with no match get
"image": null and are listed in the report for manual follow-up.

Usage:
    pip install requests
    python fill_images.py images3.json images3_enriched.json
"""
import json
import sys
import time

import requests

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "product-image-enricher/1.0 (contact: you@example.com)"}
VALID_EXT = (".jpg", ".jpeg", ".png", ".webp")

# Brand is null for some items; the descriptions make the brand clear.
BRAND_HINT = {
    "Fendi Bag Bugs": "Fendi",
    "Speed Trainers": "Balenciaga",
    "Razer Edge": "Razer",
    "Razer Barracuda": "Razer",
    "Razer Firefly": "Razer",
    "Dior Stellar Sunglasses": "Dior",
    "Beats Solo Pro": "Beats",
    "Beats Studio Buds": "Beats",
    "Breville the Smart Oven Air Fryer Pro": "Breville",
    "Highlander": "Toyota",
}


def wiki_search(query, limit=3):
    r = requests.get(API, headers=HEADERS, timeout=20, params={
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": limit, "format": "json",
    })
    r.raise_for_status()
    return [h["title"] for h in r.json()["query"]["search"]]


def page_image(title):
    r = requests.get(API, headers=HEADERS, timeout=20, params={
        "action": "query", "titles": title, "prop": "pageimages",
        "piprop": "original", "format": "json", "redirects": 1,
    })
    r.raise_for_status()
    for page in r.json()["query"]["pages"].values():
        src = page.get("original", {}).get("source")
        if src and src.startswith("https://") and src.lower().endswith(VALID_EXT):
            return src
    return None


def find_image(product):
    name = product["name"]
    brand = (product.get("brand_id") or {}).get("name") or BRAND_HINT.get(name, "")
    sub = (product.get("subcategory_id") or {}).get("name", "")
    queries = [f"{brand} {name}".strip(), f"{brand} {name} {sub}".strip()]
    seen = set()
    for q in queries:
        for title in wiki_search(q):
            if title in seen:
                continue
            seen.add(title)
            url = page_image(title)
            if url:
                return url, title
            time.sleep(0.2)
    return None, None


def main(src, dst):
    with open(src, encoding="utf-8") as f:
        doc = json.load(f)
    items = doc["data"] if isinstance(doc, dict) and "data" in doc else doc

    report = []
    for p in items:
        url, title = find_image(p)
        p["image"] = url
        report.append((p["name"], title, url))
        print(f"{'OK  ' if url else 'NULL'} {p['name']}  <-  {title}")

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=4)

    print("\n--- Review these (null, or matched page may be a different variant) ---")
    for name, title, url in report:
        if not url:
            print(f"NULL   {name}")
        else:
            print(f"CHECK  {name} -> matched page: {title}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
