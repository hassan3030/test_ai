# 15 — Attribute Facets & Variants

How attribute-level search intent — *"iPhone 13 256GB used"*, *"gold iPhone 13"*,
*"BMW 3 Series diesel under 100,000 km"* — maps onto URLs without generating an
unindexable swamp.

This is the hardest part of marketplace SEO and the most common way these projects
fail. Files [01](01-url-architecture.md) and [06](06-seo-structured-data.md) cover
three modifier dimensions (listing type, condition, city). This file adds the
fourth — **attributes** — and the rules that stop the four from multiplying.

---

## 1. The problem, with real numbers

Take one model. iPhone 13 in a mature catalog:

| Dimension | Values (+ "not specified") |
|---|---|
| Storage | 3 + 1 = 4 |
| Colour | 5 + 1 = 6 |
| Condition | 7 + `used` alias + 1 = 9 |
| Listing type | 3 + 1 = 4 |
| City | 50 + 1 = 51 |

```
4 × 6 × 9 × 4 × 51 − 1  =  44,063 modifier URLs   for ONE model
× 4,812 models          =  212,031,156
× 7 locales             =  1,484,218,092  ≈ 1.5 billion URLs
```

Every one of those would be a real, resolvable, mostly-empty page. Google's
response to that shape is not to rank it — it is to classify the site as a doorway
network and reduce crawling of the whole domain.

So the design question is never *"can we generate this URL?"* It is always
*"does this URL have independent search demand **and** independent supply?"*

---

## 2. The facet grammar

### Canonical segment order

Attributes take the slot immediately after the catalog chain, because that is how
the query reads:

```
{…catalog chain}/{attribute?}/{condition?}/{listing_type?}/in-{city?}
```

| URL | Reads as |
|---|---|
| `/…/iphone-13/256gb` | "iPhone 13 256GB" |
| `/…/iphone-13/256gb/used` | "iPhone 13 256GB used" |
| `/…/iphone-13/used/in-zagreb` | "iPhone 13 used in Zagreb" |
| `/…/iphone-13/for-rent/in-cairo` | "iPhone 13 for rent in Cairo" |
| `/…/3-series/diesel/used/in-cairo` | "3 Series diesel used in Cairo" |

> **Change from earlier drafts.** The order was `listing_type → condition → city`.
> It is now `attribute → condition → listing_type → city`. Condition moves ahead of
> listing type because it carries far more search volume, and attributes lead
> because that is where they sit in the spoken query. Any other ordering 308s to
> this one, so no URL is lost — but [01 §1](01-url-architecture.md) and
> [06](06-seo-structured-data.md) are updated to match.

### The three hard rules

```
RULE 1   At most ONE attribute facet in an indexable URL.
         /iphone-13/256gb        ✅
         /iphone-13/gold         ✅
         /iphone-13/256gb/gold   ❌ renders, noindex, canonical → /iphone-13/256gb

RULE 2   At most TWO facet dimensions in an indexable URL, and only from the
         declared pair list below. Never combinatorial.

RULE 3   Three or more dimensions NEVER indexable. Renders, noindex,
         canonical to the nearest indexable ancestor.
```

### Declared indexable combinations

| Dimensions | Example | Threshold (live listings) |
|---|---|---|
| node only | `/iphone-13` | tier rule ([06 §1](06-seo-structured-data.md)) |
| attribute | `/iphone-13/256gb` | ≥ 3 |
| condition | `/iphone-13/used` | ≥ 3 |
| listing type | `/iphone-13/for-rent` | ≥ 3 |
| city | `/iphone-13/in-zagreb` | ≥ 5 |
| attribute + condition | `/iphone-13/256gb/used` | ≥ 3 |
| condition + city | `/iphone-13/used/in-zagreb` | ≥ 3 |
| listing type + city | `/iphone-13/for-rent/in-cairo` | ≥ 3 |
| attribute + city | `/iphone-13/256gb/in-zagreb` | ≥ 5 |
| attribute + attribute | — | **never** |
| anything ≥ 3 dimensions | — | **never** |

```ts
// src/features/catalog-content/lib/facet-policy.ts
export const INDEXABLE_FACET_SHAPES = [
  [],
  ['attribute'], ['condition'], ['listingType'], ['city'],
  ['attribute', 'condition'],
  ['condition', 'city'],
  ['listingType', 'city'],
  ['attribute', 'city'],
] as const;
```

One array. Adding a shape is a deliberate, reviewable act with a demand
justification — not an emergent property of the resolver.

### The resulting ceiling

Per model, assuming 3 path-attribute values, 3 realistic conditions
(`used`, `new`, `for-parts`), 3 listing types, 10 cities with supply:

```
attribute            3
condition            3
listing type         3
city                10
attribute+condition  9
condition+city      30
listingType+city    30
attribute+city      30
                  ────
                   118  indexable-eligible URLs per model
```

Supply gating then removes 90 %+ of those in practice, landing at roughly **10–15
real indexable URLs per model**. Against 44,063. That is the entire point.

---

## 3. Facet classification

Four roles. The role decides whether a facet gets a path segment, a query param, or
nothing.

| Role | URL form | Indexable | Used for |
|---|---|---|---|
| `path` | `/…/iphone-13/256gb` | yes, per §2 | variant-defining, demand-proven |
| `query` | `/…/iphone-13?ram=8gb` | never | useful filters without independent demand |
| `none` | not in the URL | — | everything else; client state only |
| `banded` | `/…/3-series/under-100000-km` | yes, per §2 | numeric attributes |

### `path` — variant-defining and demand-proven

An attribute earns a path segment only when **all four** hold:

1. `attribute_definitions.is_variant = true`, **and**
2. `seo_role = 'path'` (a new explicit field — the flag alone is not consent), **and**
3. it is one of at most **two** `path` attributes for that subcategory, **and**
4. the specific value clears its supply threshold.

Two per subcategory is a hard cap. It is what keeps Rule 1 from being an
ever-growing negotiation.

| Subcategory | `path` attributes | Why |
|---|---|---|
| Phones | Storage, Colour | "iphone 13 256gb", "gold iphone 13" — both real query patterns |
| Laptops | RAM, Storage | how people actually shop laptops |
| Cars | Fuel type, Transmission | "bmw 320d", "automatic 3 series" |
| Shoes | — | size is personal, not a search phrase; colour is browsed, not searched |
| Real estate | Bedrooms | "3 bedroom apartment" |

Note Shoes has none. That is a correct answer, not an omission. Not every
subcategory has attribute-level search demand, and inventing facet pages where
demand does not exist is exactly the failure mode.

### `query` — filters, never indexed

```
/en/catalog/electronics/phones/apple/iphone/iphone-13?screen=6.1&ram=4gb
```

- Always `noindex, follow`, canonical to the bare path.
- Blocked in `robots.txt` (see §6) because these combinations have never been
  indexed, so there is no equity to preserve and no reason to spend crawl budget.
- Client-side only: the filter rail sets them, the server never renders a distinct
  page for them.

### `banded` — numeric attributes

A numeric attribute must **never** produce a per-value facet.
`/cars/bmw/3-series/127843-km` is a URL with a maximum audience of one.

Bands are declared per attribute:

```ts
// src/features/catalog-content/lib/facet-bands.ts
export const FACET_BANDS: Record<string, FacetBand[]> = {
  mileage: [
    { slug: 'under-50000-km',   max: 50_000 },
    { slug: 'under-100000-km',  max: 100_000 },
    { slug: 'under-150000-km',  max: 150_000 },
    { slug: 'over-150000-km',   min: 150_000 },
  ],
  'model-year': [
    { slug: '2023-2025', min: 2023, max: 2025 },
    { slug: '2020-2022', min: 2020, max: 2022 },
    { slug: '2017-2019', min: 2017, max: 2019 },
  ],
  storage: [ /* discrete, not banded — 128gb, 256gb, 512gb */ ],
};
```

Bands overlap deliberately (`under-100000-km` contains `under-50000-km`) because
that is how people search. Overlapping bands are **siblings, not ancestors** —
each is self-canonical when it clears threshold; there is no nesting.

---

## 4. Data model additions

### New: `attribute_option_values` (+ translations)

This is the enabling change. `attribute_definitions.options` is a flat JSON list of
strings, so "Gold" has nowhere to store a slug or a translation. Without this
collection, no localized facet URL is possible.

```
attribute_option_values
  id                        uuid pk
  attribute_definitions_id  uuid → attribute_definitions
  value                     string   canonical stored value, must match
                                     models_attribute_values.value and
                                     listings_attribute_values.value / selected_options
  slug                      string   base slug, e.g. "256gb"
  numeric_value             decimal  nullable; set for numeric attributes so bands can filter
  band_slug                 string   nullable; which band this value falls in
  sort                      integer
  status                    string   published | draft | archived
  listing_count             integer  cached; refreshed by the aggregates cron
  translations              alias

  UNIQUE (attribute_definitions_id, value)
  INDEX  (attribute_definitions_id, slug)

attribute_option_values_translations
  id, attribute_option_values_id, languages_code
  label                     string   "256 GB" / "٢٥٦ جيجابايت" / "256 ГБ"
  slug                      string   localized URL segment
  UNIQUE (languages_code, attribute_option_values_id)
  INDEX  (languages_code, slug)
```

This collection is also the **normalisation table**, which matters more than the
slugs. Real listing data contains `256GB`, `256 GB`, `256gb`, `256`. All four map
to one row with `slug: '256gb'`. Without that, a facet page silently misses most of
its own inventory.

### New fields on `attribute_definitions`

| Field | Type | Purpose |
|---|---|---|
| `seo_role` | string enum `path \| query \| none \| banded` | default `none`. Explicit consent — `is_variant` alone never grants a URL |
| `url_priority` | integer | which attribute wins the single path slot when a subcategory has two `path` attributes |
| `option_values` | alias (o2m) | → `attribute_option_values` |

`is_variant`, `is_filter`, `affects_price`, `slug`, `value_unit` and `is_global`
already exist and are unchanged.

### Seeding

`scripts/marketing-content/04-seed-attribute-option-values.mjs`

1. Union three sources: `attribute_definitions.options` (JSON),
   `models_attribute_values.available_options`, and distinct
   `listings_attribute_values.value` / `selected_options` from published listings.
2. Normalise: trim, NFC, collapse whitespace, lowercase for comparison, unify unit
   spacing (`256 GB` → `256GB`), strip unit when `value_unit` is set.
3. Cluster near-duplicates and **print them for review** rather than auto-merging —
   `Space Grey` / `Space Gray` / `Grey` is a judgement call, not a regex.
4. Slugify base + all seven localized slugs; leave a locale `null` to fall back to
   the base slug.
5. Detect numeric attributes, populate `numeric_value`, assign `band_slug` from
   `FACET_BANDS`.
6. `--dry-run` prints the whole plan and merges nothing.

Reserved-token and collision checks extend to option slugs:
`check-slug-collisions.mjs` must reject an option slug that collides with a
condition or listing-type token in any locale — a colour literally called "new"
would otherwise shadow the condition facet.

---

## 5. Resolution

Attributes slot into the existing modifier parser in
[01 §3](01-url-architecture.md) step 4, with one addition: attribute matching is
**scoped to the resolved node's subcategory**, because which attributes are
`path` depends on the subcategory.

```
4. Parse segments[i..] as modifiers.
   For each remaining segment, try in this order:
     a. attribute option value  — scoped to the node's subcategory via
                                  subcategories_attribute_definitions, where the
                                  definition has seo_role in ('path','banded');
                                  match localized slug then base slug
     b. condition               — CONDITION_SLUGS[locale] (+ `used` alias)
     c. listing type            — LISTING_TYPE_SLUGS[locale]
     d. city                    — segment starts with CITY_PREFIX[locale]
   Rules:
     - at most one of each dimension
     - at most ONE attribute dimension (Rule 1) — a second attribute segment is
       parsed and rendered, but forces noindex
     - out of canonical order → 308 to canonical order
     - unrecognised segment → notFound
```

Why attributes are tried first: the vocabulary is scoped and small, cities are
self-identified by their prefix, and conditions and listing types are closed global
sets. There is no realistic ambiguity left once the collision check bans overlaps.

### Filtering listings by facet

The facet page's listing query and its count both filter on
`listings_attribute_values`:

```
GET /items/listings
  ?filter[status][_eq]=published
  &filter[model_id][_eq]={modelId}
  &filter[listings_attribute_values][attribute_definitions_id][_eq]={defId}
  &filter[listings_attribute_values][value][_in]={normalisedValues}
  [&filter[condition][_in]={conditionOrAlias}]
  [&filter[location_city][_eq]={city}]
```

`{normalisedValues}` is the full set of raw spellings that map to the chosen option
row — which is why the normalisation table is load-bearing rather than cosmetic.

For `banded` attributes the filter is a numeric range against a projection of
`listings_attribute_values.value`. Where the column is a string, cast in the query
and accept that unparseable values are excluded — and report the excluded count in
the dashboard so bad data is visible rather than silently dropped.

---

## 6. Indexation and robots

The decision table in [06 §1](06-seo-structured-data.md) gains three rows:

| Condition | State | Robots | Canonical |
|---|---|---|---|
| Facet shape in `INDEXABLE_FACET_SHAPES`, above threshold, content published | **index** | `index, follow` | self |
| Facet shape not in the list (two attributes, or ≥ 3 dimensions) | noindex | `noindex, follow` | nearest indexable ancestor |
| Any `query`-role param present | noindex | `noindex, follow` | bare path |

### `robots.txt`

Replaces the per-param list in [06 §5](06-seo-structured-data.md) with a general
rule plus one exception:

```
Disallow: /*/catalog/*?
Allow:    /*/catalog/*?page=
```

Google honours the more specific `Allow`, so pagination stays crawlable while the
infinite `query`-facet space is never crawled at all. This is safe **only** because
these URLs are new: nothing has been indexed, so there is no equity to strand. For
URLs that were previously indexed, `noindex` without a `Disallow` is the correct
tool — a blocked URL is one Google cannot see the `noindex` on.

### Structured data

- Facet pages emit `CollectionPage` + `BreadcrumbList` + `ItemList`, never `Product`.
  A facet is a filtered set, not a product.
- **Exception**: a single-attribute page on a `is_variant` attribute is
  semantically a product variant, so it may emit `Product` + `AggregateOffer` with
  the attribute as `additionalProperty` — but only when `offerCount ≥ 1`, same rule
  as the model tier.
- The breadcrumb includes the facet as its own level:
  `… › iPhone 13 › 256GB › Used`.

### Sitemap

Facet URLs join the `catalog-modifiers` shard, filtered through the same shared
`getIndexationState`. Because `INDEXABLE_FACET_SHAPES` bounds the space, the shard
stays in the thousands rather than the millions.

---

## 7. Content for facet pages

A facet page cannot get its own AI-generated article — that would be 118 generation
calls per model per language and would produce near-identical text, failing the
sibling-duplication gate anyway.

Instead, facet pages **compose**:

| Section | Source |
|---|---|
| H1, meta title/description | templated from the node + facet labels, per locale |
| Lede | 2–3 templated sentences with **live** numbers: count, price range, cities |
| Editorial body | the parent node's `body`, framed as being about the model |
| Facet-specific note | new field `catalog_content_translations.facet_notes` (JSON, keyed by facet slug) — 40–80 words per `path` facet value, generated **once per node** covering all its values in a single call |
| Buying guide, FAQ, specs | inherited from the parent node |
| Price guidance | live aggregates for **this** facet + the parent's editorial prose |

So one generation call per node produces the parent article plus short notes for
each of its facet values. Cost stays at one call per node per language, not 118.

`facet_notes` shape:

```json
{
  "256gb": "The 256 GB iPhone 13 typically resells for 12–18 % above the 128 GB…",
  "512gb": "512 GB units are scarce second-hand; expect a thin market and…",
  "gold":  "Gold sold in lower volumes than Midnight or Blue, so it holds…"
}
```

The templated lede plus a facet-specific note plus genuinely different live
inventory is enough differentiation to clear the duplication gate — and it is
honest, because those *are* the real differences between the pages.

---

## 8. Relationship to a future variants system

`backend/schema/CATALOG_ANALYSIS.md` flags "No Product Variants System" as a
high-priority gap and proposes `model_variants` + `model_variant_options`. That
work is out of scope here ([00 §5](00-overview.md)), but this design is built to
absorb it.

Today `/…/iphone-13/256gb` is a **facet view** of the iPhone 13 model, filtered by
storage. When `model_variants` exists, the same URL becomes the **canonical URL of
the variant entity** — with its own row, its own content, its own SKU.

The URL does not change. That makes the eventual migration a data migration with a
`viewTransitionName`-level change to the page, not a re-architecture with a
redirect map across thousands of ranking URLs.

Two constraints to protect that path:

1. Never introduce a second URL form for the same variant (no `?variant=`,
   no `/v/{sku}`). `/…/iphone-13/256gb` must be the only address.
2. Keep `attribute_option_values.value` byte-compatible with whatever
   `model_variant_options.value` will store, so the join is trivial later.

---

## 9. Guardrails

| Guardrail | Enforcement |
|---|---|
| One attribute per indexable URL | `INDEXABLE_FACET_SHAPES` — a single array, reviewed on change |
| Max 2 `path` attributes per subcategory | validated in `apply-schema.mjs` and by `check-slug-collisions.mjs`; the dashboard rejects a third |
| No per-value numeric facets | numeric attributes must be `banded`; `seo_role: 'path'` on a numeric definition is a validation error |
| No facet page below threshold in the sitemap or in any internal link | shared `getIndexationState`, same as every other URL |
| Option-value normalisation reviewed, not auto-merged | seed script prints clusters; `--dry-run` by default |
| Facet slugs cannot shadow condition or listing-type tokens | `check-slug-collisions.mjs` in CI |
| Query params never crawled | `robots.txt` rule in §6 |
| Facet content never fully AI-generated per URL | `facet_notes` generated once per node |

### The signal to watch

In GSC → Pages, the exclusion reason **"Duplicate, Google chose a different
canonical"** rising on `/catalog/` paths means the facet policy is too loose:
Google is telling you these pages are the same page. The response is to tighten
`INDEXABLE_FACET_SHAPES` or raise thresholds — never to add more shapes.

---

## 10. Worked example

Phones subcategory. `path` attributes: Storage (`url_priority: 10`),
Colour (`url_priority: 20`).

```
INDEXABLE                                              why
/…/iphone-13                                           model tier
/…/iphone-13/256gb                                     1 attribute, 11 listings
/…/iphone-13/gold                                      1 attribute, 4 listings
/…/iphone-13/used                                      1 condition, 18 listings
/…/iphone-13/in-zagreb                                 1 city, 7 listings
/…/iphone-13/256gb/used                                attribute+condition, 8
/…/iphone-13/gold/new                                  attribute+condition, 3
/…/iphone-13/used/in-zagreb                            condition+city, 6
/…/iphone-13/for-rent/in-cairo                         listingType+city, 3
/…/iphone-13/256gb/in-zagreb                           attribute+city, 5

RENDERS, NOINDEX, canonical →
/…/iphone-13/256gb/gold           → /…/iphone-13/256gb      two attributes (Rule 1)
/…/iphone-13/256gb/used/in-zagreb → /…/iphone-13/256gb/used  3 dimensions (Rule 3)
/…/iphone-13/512gb                → /…/iphone-13             1 listing, below threshold
/…/iphone-13/gold/used/in-split   → /…/iphone-13/used        3 dimensions
/…/iphone-13?ram=4gb              → /…/iphone-13             query-role facet

308 REDIRECT →
/…/iphone-13/used/256gb           → /…/iphone-13/256gb/used  wrong order
/…/iphone-13/used/zagreb          → /…/iphone-13/used/in-zagreb  missing city prefix
/…/iphone-13/256-gb               → /…/iphone-13/256gb       non-canonical slug

404 →
/…/iphone-13/1tb                  no such option value for this model
/…/iphone-13/banana               unrecognised segment
```

Ten indexable URLs for the model, each with real inventory and a real reason to
exist. Not 44,063.
