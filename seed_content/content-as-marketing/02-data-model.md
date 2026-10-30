# 02 — Data Model

Everything here is additive. No existing collection loses a field, and no existing
field changes type — so the dashboard catalog managers, the listing flows, and the
marketplace search keep working untouched.

## 1. What already exists (reference)

Field lists confirmed from `backend/schema/*.json` (dumped 2026-01-11).

### Catalog chain

| Collection | Fields |
|---|---|
| `categories` (uuid) | `id, status, sort, date_created, name, slug, image, description, category_type, show_series, show_models, brand_label, series_label, model_label, meta_tags_id, icon` + aliases `subcategories, brands, translations` |
| `subcategories` (uuid) | `id, status, sort, category_id, name, slug, image, description, meta_tags_id, icon` + aliases `translations, attributes` |
| `brands` (uuid) | `id, status, sort, date_created, user_created, name, slug, logo, description, website, country, year_founded, is_verified, is_featured, is_active, meta_tags_id` + aliases `series, categories, translations, managed_by` |
| `series` (uuid) | `id, status, sort, date_created, brand_id, subcategory_id, name, slug, image, description, release_year` + aliases `models, translations` |
| `models` (uuid) | `id, status, sort, date_created, series_id, name, slug, model_number, description, base_price, msrp, release_date` + aliases `translations, gallery, attribute_values` |

### Translations (current content fields)

| Collection | Content fields |
|---|---|
| `categories_translations` | `name, description` |
| `subcategories_translations` | `name, description` |
| `series_translations` | `name, description` |
| `models_translations` | `name, description` |
| `brands_translations` | `name, description, tagline, short_description, about_us, mission, vision, contact_info, support_info, meta_title, meta_description, logo, cover` |

All join `languages` via `languages_code`. `languages` holds `code, name, direction`
with full codes: `en-US, ar-SA, fr-FR, es-ES, it-IT, hi-IN, ru-RU`.

### Junctions & attributes

`brands_categories` · `subcategories_attribute_definitions` · `models_files`

`attribute_definitions` — `id, status, sort, name, field_type, is_required,
options (json), is_variant, is_filter, affects_price, affects_inventory, slug,
value_unit, is_global` (+ `attribute_definitions_translations`: `name, label,
placeholder`).

Values live in two places: `models_attribute_values`
(`value, available_options, is_variant`) and `listings_attribute_values`
(`value, selected_options, source, sort`).

> **Note the gap.** `options` is a flat JSON list of strings, so an option *value*
> ("Gold", "256GB") has nowhere to store a slug or a per-language label. That is why
> [15-facets-and-variants.md](15-facets-and-variants.md) adds
> `attribute_option_values` — the enabling change for any attribute-based URL, which
> doubles as the normalisation table for `256GB` / `256 GB` / `256gb`.

### Existing SEO collections

`meta_tags` (+ `meta_tags_translations`) — `id, status, title, description,
keywords[], og_title, og_description, og_image, og_type, twitter_card,
twitter_title, twitter_description, twitter_image, canonical_url, robots,
schema_type, json_ld`. Referenced by `meta_tags_id` on `categories`,
`subcategories`, `brands`, `listings` — **not** on `series` or `models`.

`global_seo` singleton — `site_name`, `default_meta_description`, …

### Listings (the live product collection)

Relevant fields: `id (integer), status, slug, user_id, store_id, category_id,
subcategory_id, brand_id, series_id, model_id, listing_type, condition, title,
description, price, currency, negotiable, rent_price_per_day/week/month,
rental_deposit, swap_for, swap_for_categories, location (json), location_country,
location_city, location_state, shipping_available, pickup_available, views,
favorites_count, meta_tags_id, amount` + `translations, images,
listings_attribute_values`.

`listings_translations` carries `title, description, tl_dr, faqs` — the last two
populated by `app/api/seo-worker/route.ts`.

> Use the **flat** `location_city` / `location_state` / `location_country` columns
> for all filtering and aggregation. The `location` JSON is for map display.

### Notifications

Custom `notifications` collection (not `directus_notifications`):
`id (uuid), date_created, date_updated, status (active|read|archived),
recipient_id, sender_id, category (message|offer|order|review|system|promotion|alert),
subject, message, channels (json), is_read, read_at, collection, item, icon,
action_url, data (json)`.

---

## 2. New: `catalog_content`

One row per catalog entity per market. Polymorphic across the five tiers.

### Why polymorphic instead of extending five translation tables

| | Polymorphic `catalog_content` | Extend 5 × `*_translations` |
|---|---|---|
| AI pipeline | one generator, one flow, one gate | five variants to keep in sync |
| Admin UI | one collection to review and moderate | five places to look |
| Adding a 6th tier later | free | another migration + another code path |
| Risk to existing collections | zero — they are untouched | schema churn on tables the catalog dashboard writes to |
| Relational integrity on the entity link | none (soft `entity_id`) | enforced by Directus |
| Queries per page | one extra batched read | included in the entity read |

The two costs are real but bounded: the soft reference is protected by a
uniqueness constraint plus an orphan-sweep script, and the extra read is one
filtered query per page that ISR caches.

### Fields

| Field | Type | Interface / notes |
|---|---|---|
| `id` | uuid | PK, `special: uuid` |
| `entity_type` | string | dropdown: `category, subcategory, brand, series, model`. Required. |
| `entity_id` | uuid | soft reference to the tier's row. Required. |
| `primary_market` | string (2) | ISO-3166-1 alpha-2, nullable. `null` = global/default content. |
| `status` | string | dropdown: `draft, in_review, published, archived`. Default `draft`. |
| `ai_generated` | boolean | default `false` |
| `ai_model` | string | e.g. `gpt-5.5`; the model that produced the current version |
| `ai_generated_at` | timestamp | drives the regeneration cooldown |
| `source_hash` | string (64) | SHA-256 of the generation input bundle — idempotency key |
| `content_version` | integer | default `1`, incremented on each accepted regeneration |
| `quality_score` | decimal(3,2) | 0.00–1.00, from the quality gate |
| `gate_report` | json | `{ passed: boolean, checks: [{name, passed, detail}] }` — why it did or didn't publish |
| `reviewed_by` | uuid | → `directus_users` |
| `reviewed_at` | timestamp | |
| `hero_image` | uuid | → `directus_files`, nullable; falls back to the entity's own `image` / `logo` |
| `listing_count` | integer | cached count of published listings under this node. Default `0`. |
| `subscriber_count` | integer | cached count of confirmed `catalog_alerts` on this node. Default `0`. |
| `price_min` / `price_max` / `price_median` | decimal | cached aggregates |
| `price_currency` | string (3) | currency the aggregates are expressed in |
| `last_counted_at` | timestamp | when the cached aggregates were refreshed |
| `date_created` / `date_updated` | timestamp | `special: date-created` / `date-updated` |
| `user_created` / `user_updated` | uuid | `special: user-created` / `user-updated` |
| `translations` | alias | o2m → `catalog_content_translations` |

**Constraints**

```sql
UNIQUE (entity_type, entity_id, primary_market)
INDEX  (entity_type, entity_id)
INDEX  (status)
```

**Directus display template**: `{{entity_type}} · {{translations.h1}}`

## 3. New: `catalog_content_translations`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | PK auto-increment (matches the existing `*_translations` convention) |
| `catalog_content_id` | uuid | → `catalog_content`, o2m field `translations` |
| `languages_code` | string | → `languages.code` |
| `status` | string | dropdown `draft, published`. Per-language coverage — English can be live while Hindi is still drafting. |
| `meta_title` | string (60) | hard cap enforced by the gate |
| `meta_description` | string (160) | hard cap enforced by the gate |
| `keywords` | json | `string[]` |
| `h1` | string | the visible page heading; often differs from `meta_title` |
| `lede` | text | 60–120 words: the "what is this" opening paragraph |
| `body` | text | rich HTML from Tiptap (already a dependency). ≥ 250 words. |
| `buying_guide` | text | rich HTML: what to check, how to compare, red flags |
| `price_guidance` | text | rich HTML: what drives price at this node, how to read the live range |
| `tl_dr` | text | 40–60 words. Same contract as `listings_translations.tl_dr` — feeds `llms.txt` and AI answer engines. |
| `faqs` | json | `[{ question, answer }]`, 3–6 entries |
| `key_specs` | json | `[{ label, value }]` — series/model tiers, seeded from `models_attribute_values` then enriched |
| `comparison_notes` | text | model tier: how this model compares to its siblings in the same series |
| `slug_suggestion` | string | AI's proposed localized slug; promoted into `<tier>_translations.slug` after slugify + uniqueness check |
| `og_image` | uuid | → `directus_files`, nullable |
| `word_count` | integer | computed on write from `body`; the thin-content gate reads this |
| `reading_time_minutes` | integer | computed; displayed in the UI |

**Constraints**

```sql
UNIQUE (catalog_content_id, languages_code)
INDEX  (languages_code, status)
```

### Metadata precedence per page

```
1. meta_tags row linked from the entity, IF meta_tags.status = 'published'
   (preserves work editors already did on categories / subcategories / brands)
2. catalog_content_translations for the request locale, IF status = 'published'
3. dynamic fallback: entity name + live aggregates
   (reuse the shape in app/[locale]/marketplace/categories/[subcat]/metadata.ts)
```

`series` and `models` deliberately get **no** `meta_tags_id` — step 2 covers them,
and adding the field would mean two competing sources of truth for two tiers.

## 4. New: localized slug fields

Add one field to each of the five translation collections:

```
categories_translations.slug     string, nullable, indexed
subcategories_translations.slug  string, nullable, indexed
brands_translations.slug         string, nullable, indexed
series_translations.slug         string, nullable, indexed
models_translations.slug         string, nullable, indexed
```

- `nullable` on purpose: a missing localized slug falls back to the entity's base
  `slug`, so nothing breaks before backfill completes.
- Directus field note: *"URL segment for this language. Leave empty to use the
  base slug. Must be unique within its parent and language."*
- Uniqueness: see [01-url-architecture.md §4](01-url-architecture.md).

Migration adds:

```sql
CREATE UNIQUE INDEX categories_translations_lang_slug_uq
  ON categories_translations (languages_code, slug) WHERE slug IS NOT NULL;
CREATE UNIQUE INDEX brands_translations_lang_slug_uq
  ON brands_translations (languages_code, slug) WHERE slug IS NOT NULL;
CREATE INDEX subcategories_translations_lang_slug_ix
  ON subcategories_translations (languages_code, slug);
CREATE INDEX series_translations_lang_slug_ix
  ON series_translations (languages_code, slug);
CREATE INDEX models_translations_lang_slug_ix
  ON models_translations (languages_code, slug);
```

Parent-scoped tiers get a plain index plus app-layer + CI enforcement, because a
portable composite unique across a relation is not expressible here.

## 5. New: `catalog_slug_history`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | PK |
| `entity_type` | string | `category, subcategory, brand, series, model` |
| `entity_id` | uuid | |
| `languages_code` | string | nullable — `null` means the base `slug` changed |
| `old_slug` | string | |
| `date_created` | timestamp | |

```sql
INDEX (entity_type, languages_code, old_slug)
```

Written by the dashboard catalog write routes **before** applying a slug change.
Rows are never deleted. The resolver reads this to 308 stale inbound links.

## 6. New: `geo_locations` (+ `geo_locations_translations`)

Powers the city modifier ("iPhone 13 used **in Zagreb**").

### `geo_locations`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `country` | string (2) | ISO-3166-1 alpha-2 |
| `region` | string | state / governorate / county, nullable |
| `city` | string | canonical English name |
| `slug` | string | base slug |
| `latitude` / `longitude` | decimal | nullable; used for "nearby cities" links |
| `population` | integer | nullable; a tiebreaker for which cities get pages |
| `is_active` | boolean | default `true`. Inactive cities resolve but are never linked or indexed. |
| `listing_count` | integer | cached; refreshed by cron |
| `sort` | integer | |
| `status` | string | `published, draft, archived` |
| `translations` | alias | o2m |

```sql
UNIQUE (country, slug)
INDEX  (country, city)
INDEX  (is_active, listing_count)
```

### `geo_locations_translations`

| Field | Type |
|---|---|
| `id` | integer PK |
| `geo_locations_id` | uuid |
| `languages_code` | string |
| `name` | string — e.g. `زغرب`, `Загреб` |
| `slug` | string — the localized URL segment |
| `blurb` | text, nullable — one or two sentences about buying/selling in this city, used on geo pages |

```sql
UNIQUE (languages_code, geo_locations_id)
INDEX  (languages_code, slug)
```

### Seeding

`scripts/marketing-content/03-seed-geo-locations.mjs`:

1. Read distinct `(location_country, location_city, location_state)` from
   published `listings` with a count per group.
2. Merge a curated top-cities list per launch market (kept in the script as a
   plain data block, so it is reviewable in diff).
3. Normalise city names (trim, title-case, collapse known aliases like
   `Cairo` / `القاهرة` / `Kairo` into one row).
4. Slugify base + all seven localized slugs. Localized names for major cities are
   seeded from the curated block; anything missing is left `null` and the resolver
   falls back to the base slug.
5. `--dry-run` prints the plan; without it, upserts by `(country, slug)`.

## 6b. New: `attribute_option_values` (+ translations)

Specified in full in [15 §4](15-facets-and-variants.md). Summarised here so this
file stays the complete collection inventory:

```
attribute_option_values
  id, attribute_definitions_id → attribute_definitions,
  value, slug, numeric_value, band_slug, sort, status, listing_count, translations
  UNIQUE (attribute_definitions_id, value)
  INDEX  (attribute_definitions_id, slug)

attribute_option_values_translations
  id, attribute_option_values_id, languages_code, label, slug
  UNIQUE (languages_code, attribute_option_values_id)
  INDEX  (languages_code, slug)
```

Plus three new fields on the existing `attribute_definitions`:

| Field | Type | Purpose |
|---|---|---|
| `seo_role` | enum `path \| query \| none \| banded` | default `none`. Explicit consent — `is_variant` alone never grants a URL |
| `url_priority` | integer | which attribute wins the single path slot when a subcategory has two `path` attributes |
| `option_values` | alias o2m | → `attribute_option_values` |

## 7. New: `catalog_alerts`

Demand capture: "notify me when this is available". Full behaviour in
[07-availability-alerts.md](07-availability-alerts.md).

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `date_created` | timestamp | |
| `user_id` | uuid | → `directus_users`, nullable (guest subscriptions) |
| `email` | string | nullable; required when `user_id` is null. Never returned by any API response. |
| `entity_type` | string | `category, subcategory, brand, series, model` |
| `entity_id` | uuid | the node subscribed to |
| `condition` | string | nullable; a `listings.condition` value or the `used` alias |
| `listing_type` | string | nullable; `sell, rent, swap` |
| `city_id` | uuid | → `geo_locations`, nullable |
| `max_price` | decimal | nullable |
| `currency` | string (3) | nullable; interpretation of `max_price` |
| `locale` | string | which of the 7 locales to notify in |
| `status` | string | `pending, confirmed, notified, unsubscribed` |
| `token` | string (64) | unique; used for confirm + unsubscribe links |
| `confirmed_at` | timestamp | |
| `last_notified_at` | timestamp | throttle |
| `notify_count` | integer | default `0` |
| `source_path` | string | the `/catalog/` path they subscribed from — useful for the demand report |

```sql
UNIQUE (token)
UNIQUE (user_id, entity_type, entity_id, condition, listing_type, city_id)
UNIQUE (email,   entity_type, entity_id, condition, listing_type, city_id)
INDEX  (entity_type, entity_id, status)
```

The two partial uniques prevent duplicate subscriptions from the same person to
the same permutation, whether they are logged in or not.

## 8. Permissions

### Public role

Read-only, filtered, field-limited. **No wildcard reads** — the go-live public-role
audit found live PII leaks caused by exactly that pattern.

| Collection | Permission | Filter | Fields |
|---|---|---|---|
| `catalog_content` | read | `status = published` | `id, entity_type, entity_id, primary_market, hero_image, listing_count, price_min, price_max, price_median, price_currency, translations` |
| `catalog_content_translations` | read | `status = published` | `id, catalog_content_id, languages_code, meta_title, meta_description, keywords, h1, lede, body, buying_guide, price_guidance, tl_dr, faqs, key_specs, comparison_notes, og_image, reading_time_minutes` |
| `geo_locations` | read | `status = published AND is_active = true` | `id, country, region, city, slug, latitude, longitude, listing_count, translations` |
| `geo_locations_translations` | read | — | `id, geo_locations_id, languages_code, name, slug, blurb` |
| `catalog_slug_history` | read | — | `entity_type, entity_id, languages_code, old_slug` |
| `attribute_option_values` | read | `status = published` | `id, attribute_definitions_id, value, slug, numeric_value, band_slug, listing_count, translations` |
| `attribute_option_values_translations` | read | — | `id, attribute_option_values_id, languages_code, label, slug` |
| `*_translations.slug` (5 tiers) | read | — | add `slug` to each existing public read allowlist |
| `catalog_alerts` | **none** | — | — |

Explicitly **not** exposed publicly: `catalog_content.gate_report`,
`quality_score`, `source_hash`, `ai_*`, `reviewed_*`, `subscriber_count`,
`user_created/updated`; and every field of `catalog_alerts`.

Note: `/catalog/` pages are server-rendered with `createAdminClient`, so they do not
depend on the public role. Public read exists so the collections can also be
consumed by the client-side filter components and by any future public API
consumer without a second code path.

### Authenticated user role

| Collection | Permission | Scope |
|---|---|---|
| `catalog_alerts` | create | `user_id = $CURRENT_USER` |
| `catalog_alerts` | read / update / delete | `user_id = $CURRENT_USER` |

Guest (email) alerts are created by the API route with the admin token after
rate-limit and double-opt-in checks, never directly by the public role.

### Manager / moderator role

Full read on `catalog_content*` including `gate_report`; update on `status`,
`reviewed_by`, `reviewed_at`, and every translation content field. Read on
`catalog_alerts` **excluding `email`** (aggregate demand reporting does not need
the address).

> The app's dashboard PATCH routes use the Directus **admin token**, which
> bypasses Directus policies. So every one of these rules must *also* be enforced
> in the route handler — the same belt-and-braces pattern already used for the
> read-only AI settings.

## 9. Applying the schema

Directus schema, permissions and flows live in the Directus database and do
**not** travel with a code deploy. Everything ships as a re-runnable script.

```
scripts/marketing-content/
  apply-schema.mjs            creates/updates collections, fields, relations
  apply-permissions.mjs       public + user + manager policies
  seed-geo-locations.mjs      cities from listings + curated list
  seed-attribute-option-values.mjs  option slugs, translations, numeric bands
  build-alert-flows.mjs       the listings→alerts matching flow
  backfill-slugs.mjs          localized slugs for existing entities
  check-slug-collisions.mjs   CI audit
  sweep-orphans.mjs           catalog_content rows whose entity_id no longer exists
docs/content-as-marketing/directus-snapshot/
  collections.json  fields.json  relations.json  permissions.json  flows.json
```

`apply-schema.mjs` must be **idempotent**: check for the collection/field before
creating, and PATCH rather than POST when it exists. Model it on
`scripts/rental/` and `scripts/notifications/build-store-team-notification-flows.mjs`,
both of which are already re-runnable.

### Rollout order

```
dev      → apply-schema, apply-permissions, seed-geo-locations, backfill-slugs
         → verify with check-slug-collisions + the queries in 11-verification.md
         → snapshot into docs/content-as-marketing/directus-snapshot/
prod-clone → replay the same four scripts, diff against the dev snapshot
prod     → replay, then re-verify. Public-role permissions in particular must be
           confirmed on prod: they are DB state, not code.
```

## 10. Data-integrity guards

| Guard | Where |
|---|---|
| `catalog_content` orphans (entity deleted) | the orphan sweep in the refresh cron, run weekly; archives rather than deletes |
| Duplicate `catalog_content` for one entity+market | DB unique constraint |
| Slug collisions | app-layer check + `check-slug-collisions.mjs` in CI |
| Reserved-token slugs | rejected at write time in the dashboard catalog routes |
| Stale cached aggregates | `last_counted_at` + the refresh cron; the page also shows live counts, so a stale cache never shows a wrong number to a user — only to the indexation gate, which tolerates an hour of lag |
| Alert duplication | two partial unique constraints |
| PII in logs | never log `catalog_alerts.email`; log the `id` |
