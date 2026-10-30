# 01 — URL Architecture

## 1. The scheme

All catalog content lives under a single `/catalog/` namespace inside the existing
`[locale]` segment.

```
/{locale}/catalog                                                          catalog hub
/{locale}/catalog/{category}                                               tier 1
/{locale}/catalog/{category}/{subcategory}                                 tier 2
/{locale}/catalog/{category}/{subcategory}/{brand}                         tier 3
/{locale}/catalog/{category}/{subcategory}/{brand}/{series}                tier 4
/{locale}/catalog/{category}/{subcategory}/{brand}/{series}/{model}        tier 5
```

Modifiers append in a **fixed canonical order** — attribute, then condition, then
listing type, then city. City segments carry a localized `in-` prefix so they read
like the search query and are self-identifying to the resolver:

```
{…catalog}/{attribute?}/{condition?}/{listing_type?}/in-{city?}
```

The attribute slot (`256gb`, `gold`, `diesel`, `under-100000-km`) and the rules that
stop the four dimensions multiplying into millions of URLs are specified in
[15-facets-and-variants.md](15-facets-and-variants.md). Read that before touching
the modifier parser — the constraints there are what keep this scheme safe.

Worked examples:

```
/en/catalog/electronics
/en/catalog/electronics/phones
/en/catalog/electronics/phones/apple
/en/catalog/electronics/phones/apple/iphone
/en/catalog/electronics/phones/apple/iphone/iphone-13
/en/catalog/electronics/phones/apple/iphone/iphone-13/256gb
/en/catalog/electronics/phones/apple/iphone/iphone-13/used
/en/catalog/electronics/phones/apple/iphone/iphone-13/256gb/used
/en/catalog/electronics/phones/apple/iphone/iphone-13/used/in-zagreb
/en/catalog/electronics/phones/apple/iphone/iphone-13/for-rent/in-cairo
/ar/catalog/الكترونيات/هواتف/apple/iphone/iphone-13/مستعمل/في-زغرب
```

### Why `/catalog/`

Google's URL guidance is short: use readable words, keep the hierarchy logical,
keep URLs stable. Every segment here is a word a person would type, and the depth
of the path is the tier — so `/catalog/` gives the resolver a namespace where
**path depth alone identifies the tier**, with no ambiguity to guard against.

| Alternative | Why rejected |
|---|---|
| `/{locale}/{category}/…` (root level, no prefix) | Shortest and most keyword-dense — the strongest option on pure SEO grounds. Rejected for architectural safety: a root-level catch-all swallows every unmatched URL under the locale, and every catalog slug then competes with all 14 existing top-level routes (`about`, `auth`, `customer-service`, `dashboard`, `help`, `marketplace`, `messages`, `notifications`, `offer`, `onboarding`, `orders`, `privacy-policy`, `terms-and-conditions`, `tracking`) plus every route added in future. Next resolves static segments before catch-alls, so a new app route would silently orphan a same-named category page. |
| `/{locale}/c/…` | A single letter tells neither a user nor a crawler anything, and shows as filler in the SERP breadcrumb (`swibba.com › c › Electronics`). Same namespace safety as `/catalog/` for no readability. |
| `/{locale}/marketplace/{category}/…` | Collides with `/{locale}/marketplace/[slug]` (product, resolves `{slug}-{id}`), `/marketplace/store/[slug]` and `/marketplace/brand/[slug]`. Every catalog slug would need a reserved-word guard against those three. Also 11 characters of no keyword value. |
| `/{locale}/buy/…` or `/shop/…` | Misleading: these pages cover buying, renting **and** swapping. A prefix that narrows the intent is worse than one that describes the thing. |
| `/{locale}/category/…`, `/{locale}/model/…` (flat per tier) | Zero ambiguity, but five unrelated URL families. Loses the visible hierarchy that makes a topical cluster legible to search engines and readable in a SERP breadcrumb. |
| Flattening the model tier (`/electronics/phones/apple-iphone-13`) | Shorter model URLs, but `series` has no natural slot, a model slug can collide with a brand slug at the same depth, and the `Apple › iPhone › iPhone 13` chain breaks exactly where commercial intent is highest. |

`/catalog/` costs one non-keyword segment. It buys complete namespace isolation:
no reserved top-level word list, no first-segment fast-404 guard, and no risk that
adding `/{locale}/blog` next quarter breaks a category page.

### Why the full five-level chain

`apple/iphone/iphone-13` repeats "iphone" twice, which looks redundant until you
see the SERP breadcrumb it produces:

```
swibba.com › Catalog › Electronics › Phones › Apple › iPhone › iPhone 13
```

That is natural product hierarchy, not keyword stuffing — the same shape car
marketplaces use (`/cars/bmw/3-series/320i`). Google's warning is about stuffing
repeated keywords into a URL for ranking; a genuine parent-child chain is the
case its own documentation recommends. The topical-cluster signal and the
breadcrumb legibility are worth more than four saved characters.

## 2. Route files

```
app/[locale]/catalog/page.tsx                       catalog hub — all categories
app/[locale]/catalog/[...path]/page.tsx             tiers 1–5 + modifiers
app/[locale]/catalog/[...path]/layout.tsx           JSON-LD injection
app/[locale]/catalog/[...path]/metadata.ts          generateMetadata helpers
app/[locale]/catalog/[...path]/opengraph-image.tsx  generated OG cards (phase 6)
```

A single catch-all rather than five nested dynamic folders, because the tier is a
function of how many segments resolve — not of a fixed folder depth. A category
with `show_series = false` legitimately produces a shorter chain.

## 3. The resolver

`src/features/catalog-content/lib/resolve-path.ts`

### Contract

```ts
export type CatalogTier = 'category' | 'subcategory' | 'brand' | 'series' | 'model';

export interface CatalogChainNode {
  tier: CatalogTier;
  id: string;                        // uuid
  name: string;                      // localized
  slug: string;                      // slug used in THIS locale's URL
  baseSlug: string;                  // entity.slug (English/base)
  image: string | null;              // directus file id
}

export interface CatalogModifiers {
  /** At most one is indexable; a second parses but forces noindex. */
  attributes?: Array<{
    definitionId: string;
    optionValueId: string;
    slug: string;                    // slug used in THIS locale's URL
    label: string;                   // localized
    /** Set for banded numeric attributes, e.g. "under-100000-km". */
    band?: string;
  }>;
  condition?: string;                // listings.condition enum value, or the `used` alias
  listingType?: 'sell' | 'rent' | 'swap';
  cityId?: string;                   // geo_locations.id
  city?: { id: string; name: string; slug: string; country: string };
}

export interface ResolvedCatalogPath {
  tier: CatalogTier;
  entity: CatalogChainNode;          // the deepest resolved node
  chain: CatalogChainNode[];         // root → entity, inclusive
  modifiers: CatalogModifiers;
  locale: Locale;
  /** Canonical path for THIS locale, leading slash, no locale prefix. */
  canonicalPath: string;
  /** Same node+modifiers expressed in every locale — feeds hreflang. */
  localizedPaths: Record<Locale, string>;
}

export type ResolveResult =
  | { kind: 'ok'; resolved: ResolvedCatalogPath }
  | { kind: 'redirect'; to: string }       // 308, canonical form
  | { kind: 'notFound' };

export async function resolveCatalogPath(
  segments: string[],
  locale: Locale,
): Promise<ResolveResult>;
```

### Algorithm

```
input: segments[], locale

1. If segments is empty → the hub page handles it (separate route).

2. i = 0; parent = null; chain = []
   For each expected tier in [category, subcategory, brand, series, model]:
     a. If i >= segments.length → break (chain ends here; shorter chains are valid).
     b. Try to match segments[i] as that tier, scoped to `parent`:
          - first against <tier>_translations.slug WHERE languages_code = code(locale)
          - then against <tier>.slug            (base slug)
        Scoping rules:
          category      → no parent scope
          subcategory   → subcategories.category_id = category.id
          brand         → brands_categories links brand to category.id
                           AND a series exists with (brand_id = brand.id
                                                     AND subcategory_id = subcategory.id)
          series        → series.brand_id = brand.id
                           AND series.subcategory_id = subcategory.id
          model         → models.series_id = series.id
        Also require status = 'published' / is_active.
     c. On match: push to chain; parent = matched; i++
        On no match: break out of the tier loop.

3. If chain is empty → notFound.

4. Parse segments[i..] as modifiers, trying each remaining segment in this order:
     attribute    ← attribute_option_values(+translations).slug, SCOPED to the node's
                    subcategory via subcategories_attribute_definitions, where the
                    definition has seo_role in ('path','banded')
     condition    ← CONDITION_SLUGS[locale]      (e.g. new | used | like-new | …)
     listingType  ← LISTING_TYPE_SLUGS[locale]   (e.g. for-sale | for-rent | for-swap)
     city         ← segment starts with CITY_PREFIX[locale] ("in-" / "في-" / …);
                    strip the prefix, then match geo_locations(+translations).slug
                    where is_active = true
   Rules:
     - each modifier kind may appear at most once
     - a SECOND attribute segment parses and renders, but forces noindex
       (facet Rule 1 — see 15-facets-and-variants.md)
     - an unrecognised segment → notFound
     - modifiers out of canonical order → redirect to canonical order
     - a bare city slug without the prefix (…/used/zagreb) → redirect to …/used/in-zagreb
     - a city modifier without a catalog node is not reachable (chain is non-empty by step 3)

5. If any segment matched a BASE slug while a localized slug exists for `locale`
   → redirect to the fully localized path.

6. If a segment matched nothing but appears in `catalog_slug_history` for this
   (entity_type, languages_code) → redirect to the current slug's path.

7. Build canonicalPath and localizedPaths (see §5), return ok.
```

### Precedence and the collision guard

**A catalog match always wins over a modifier match at the same position.** A
brand literally named "used" would otherwise shadow the condition modifier.

To make that impossible rather than merely unlikely, catalog slugs are forbidden
from equalling any reserved token, in any locale:

```ts
// src/features/catalog-content/lib/reserved-slugs.ts
export const RESERVED_CATALOG_SLUGS = new Set([
  // listing types, all locales
  ...Object.values(LISTING_TYPE_SLUGS).flatMap(Object.values),
  // conditions, all locales
  ...Object.values(CONDITION_SLUGS).flatMap(Object.values),
  // structural
  'page', 'p', 'all',
]);
```

Enforced in two places:

1. **On write** — the dashboard catalog routes under
   `app/api/dashboard/catalog/{categories,subcategories,brands,series,models}/`
   reject a slug (base or localized) that is in `RESERVED_CATALOG_SLUGS`.
2. **As an audit** — `scripts/marketing-content/08-check-slug-collisions.mjs` scans
   all five collections plus their translations and exits non-zero on any
   collision, any duplicate within a scope, and any empty slug. Run it in CI.

Note what is **not** in the set, and why:

- **Top-level app route names** (`about`, `dashboard`, `help`, …). The `/catalog/`
  prefix isolates the namespace completely, so a category slugged `help` is
  perfectly safe. This is the whole return on spending one segment on the prefix.
- **City slugs.** Cities are always written `in-{slug}`, so a city segment can
  never be mistaken for a catalog slug or a condition — and a brand and a city may
  freely share a name. The `in-` prefix converts what was a precedence rule into a
  structural guarantee.
- **Attribute option slugs** are checked separately: `check-slug-collisions.mjs`
  rejects an option slug that collides with a condition or listing-type token in any
  locale. A colour literally named "new" would otherwise shadow the condition facet.

### Helpers to reuse

Do not re-derive the locale mapping or the translation-picking logic — it already
exists in `src/features/catalog/utils/localization.ts`:

| Need | Helper |
|---|---|
| `en` → `en-US` (the `languages.code` form Directus stores) | `getLanguageCode(locale)` |
| Localized `name` + `description` with `en-US` then base fallback | `getLocalizedContent(item, locale)` |
| Localized `name` only | `getLocalizedName(item, locale)` |

The resolver's slug lookup follows the same fallback ladder those helpers use:
requested language → `en-US` → the entity's own base column. Keeping the ladder
identical is what makes a page's URL, heading and breadcrumb agree with each other.

### Caching inside the resolver

Each tier lookup is a small filtered Directus read. To keep a five-segment path
from costing five round trips per request:

- The **modifier vocabulary** (`geo_locations` + translations, condition and
  listing-type slug maps) is loaded once and cached with `unstable_cache`
  (tag `geo:all`, `revalidate: 86400`).
- The **category and subcategory maps** are small and fully cached
  (tags `catalog:categories:all`, `catalog:subcategories:all`).
- Brand / series / model lookups are per-request `cache()`-wrapped point reads,
  themselves wrapped in `unstable_cache` keyed by `(parentId, slug, locale)`.

Because pages are ISR-cached (see [04](04-rendering-caching.md)), resolution
happens on cache miss only.

## 4. Localized slugs

### Schema change

Add a `slug` field to all five translation collections:

| Collection | New field | Scope for uniqueness |
|---|---|---|
| `categories_translations` | `slug` | `languages_code` (global) |
| `subcategories_translations` | `slug` | `languages_code` + parent `category_id` |
| `brands_translations` | `slug` | `languages_code` (global) |
| `series_translations` | `slug` | `languages_code` + parent `subcategory_id` |
| `models_translations` | `slug` | `languages_code` + parent `series_id` |

`brands_translations` already has `meta_title` / `meta_description` / `logo` /
`cover`, so adding `slug` there is consistent with how that table is already used.

Full field definitions in [02-data-model.md](02-data-model.md).

### Uniqueness enforcement

Directus cannot express a composite unique constraint across a relation, so:

- **App layer** — the dashboard catalog write routes validate uniqueness within
  scope before PATCH/POST and return `409` with the conflicting row.
- **DB layer** — a migration adds `UNIQUE (languages_code, slug)` on
  `categories_translations` and `brands_translations` (globally unique tiers).
  For the parent-scoped tiers a partial/expression index is not portable, so
  those rely on the app layer plus the CI audit script.
- **Audit** — `check-slug-collisions.mjs` is the backstop.

### Script and encoding

Non-Latin slugs keep their native script:

```
/ar/catalog/الكترونيات/هواتف
/ru/catalog/электроника/телефоны
/hi/catalog/इलेक्ट्रॉनिक्स/फ़ोन
```

Notes:

- URLs are percent-encoded on the wire; browsers and Google display them decoded.
- Next.js decodes dynamic segments before they reach the resolver — compare
  against stored slugs **after** `decodeURIComponent` and NFC-normalise both
  sides (`String.prototype.normalize('NFC')`) so visually identical Arabic
  strings match.
- Slugify with a Unicode-aware helper: lowercase, NFC normalise, collapse
  whitespace to `-`, strip `/ ? # [ ] @ % & = + " ' < > \` and control chars,
  trim leading/trailing `-`. Do **not** transliterate to ASCII — that defeats
  the purpose.
- Latin brand and model slugs (`apple`, `iphone-13`) stay identical across
  locales. That is correct: they are proper nouns, and keeping them stable makes
  cross-locale URLs recognisable.

### Slug history

Every slug change writes a `catalog_slug_history` row before the update:

```
(entity_type, entity_id, languages_code, old_slug, date_created)
```

Step 6 of the resolver checks it and issues a permanent redirect. Rows are never
deleted — a 10-year-old inbound link should still land.

## 5. Canonicals, hreflang, and `localizedPaths`

### Canonical URL

Exactly one canonical URL per (node + modifiers + locale):

```
{NEXT_PUBLIC_APP_URL}/{locale}{canonicalPath}
```

`canonicalPath` is built from the resolved chain using **this locale's** slugs,
in canonical modifier order. Every other spelling of the same thing (base slugs
under a localized locale, historical slugs, out-of-order modifiers) redirects to
it with a 308.

Pages that fail the indexation gate carry `noindex, follow` **and** a canonical
pointing at their nearest indexable ancestor — see
[06-seo-structured-data.md](06-seo-structured-data.md).

### hreflang

`localizedPaths` is built by re-projecting the resolved chain through every
locale's translations in one pass — the chain's translations are already fetched,
so this costs nothing extra:

```ts
alternates: {
  canonical: `${APP_URL}/${locale}${resolved.canonicalPath}`,
  languages: {
    // Use localeConfig[l].hreflang from src/i18n/config.ts, not the bare locale
    'en-US': `${APP_URL}/en${resolved.localizedPaths.en}`,
    'ar-SA': `${APP_URL}/ar${resolved.localizedPaths.ar}`,
    'fr-FR': `${APP_URL}/fr${resolved.localizedPaths.fr}`,
    'es-ES': `${APP_URL}/es${resolved.localizedPaths.es}`,
    'it-IT': `${APP_URL}/it${resolved.localizedPaths.it}`,
    'hi-IN': `${APP_URL}/hi${resolved.localizedPaths.hi}`,
    'ru-RU': `${APP_URL}/ru${resolved.localizedPaths.ru}`,
    'x-default': `${APP_URL}/en${resolved.localizedPaths.en}`,
  },
}
```

`localeConfig` in `src/i18n/config.ts` already holds the `hreflang` value per
locale (`en-US`, `ar-SA`, …) — read it from there rather than hardcoding.

Rules:

- A locale is only listed if the chain resolves in it. If a model has no Hindi
  translation, `hi` falls back to base slugs and is still listed (the page
  renders in Hindi chrome with fallback content) — but it is **excluded** if the
  page would be `noindex` in that locale.
- `x-default` always points at `en`.
- The same alternates must be mirrored in the sitemap. See [06](06-seo-structured-data.md).

### Pagination

Listing pagination on `/catalog/` pages uses a query param:

```
/en/catalog/electronics/phones?page=3
```

- `page=1` is never emitted; the bare path is page 1.
- `page ≥ 2` gets `noindex, follow` and a self-referencing canonical.
- `rel=next/prev` is not used (deprecated by Google). Discovery relies on the
  server-rendered links in the grid.

Filter query params (`?condition=`, `?min_price=`) are **client-side only** on
`/catalog/` pages and always `noindex`. Anything worth indexing gets a path-based
modifier instead.

## 6. Migration from the existing routes

| Existing route | Action | Implementation |
|---|---|---|
| `app/[locale]/marketplace/categories/page.tsx` | 308 → `/{locale}/catalog` | `permanentRedirect()` at the top of the server component |
| `app/[locale]/marketplace/categories/[subcat]/page.tsx` + `layout.tsx` + `metadata.ts` | 308 → `/{locale}/catalog/{category}` (localized slug) | Replace `page.tsx` body with a lookup + `permanentRedirect()`. Keep the folder so old links keep resolving. |
| `app/[locale]/marketplace/brand/[slug]/page.tsx` + `metadata.ts` | 308 → `/{locale}/catalog/{cat}/{subcat}/{brand}` | Pick the brand's primary chain: its first `brands_categories` entry, then the subcategory of its highest-`listing_count` series. If no chain exists, keep the current page (an orphan brand has nowhere to redirect to). |
| `app/[locale]/marketplace/brands/page.tsx` | keep | It is a brand *directory*, still useful; add links into `/catalog/` |
| `app/[locale]/marketplace/page.tsx` | keep | Remains the faceted search surface. `/catalog/` pages deep-link into it with prefilled filters. |
| `app/[locale]/marketplace/[slug]` | keep, unchanged | Product detail. Note the `-{id}` suffix requirement. |

Why `permanentRedirect()` (which emits **308**) rather than a 301:

- Next's `redirect()` emits 307 and `permanentRedirect()` emits 308. Both are the
  method-preserving equivalents of 302/301.
- Google treats 308 exactly as it treats 301 for canonicalisation and link-equity
  consolidation.
- Doing it in `proxy.ts` instead would require a Directus lookup inside
  middleware on every request, which is worse than doing it once per ISR miss.

The old routes are **never deleted**. They cost one cached redirect and preserve
whatever authority those URLs accumulated.

### Fix shipped with the migration

`app/[locale]/marketplace/categories/[subcat]/metadata.ts` currently has two
different canonical URLs depending on which branch runs:

```ts
// buildMetadataFromDirectus
const canonicalUrl = metaTags.canonical_url || generateCanonicalUrl(slug, locale);
// → `${APP_URL}/${locale}/marketplace/categories/${slug}`

// buildMetadataDynamically
const canonicalUrl = `${APP_URL}/${locale}/marketplace?cat=${slug}`;
```

Both must resolve to the new `/catalog/` canonical. Since the page becomes a redirect,
the simplest correct fix is to delete both builders along with the page body —
the redirect target supplies its own canonical.

## 7. Reserved vocabulary reference

### Listing types

| Value in `listings.listing_type` | `en` | `ar` | `fr` | `es` | `it` | `hi` | `ru` |
|---|---|---|---|---|---|---|---|
| `sell` | `for-sale` | `للبيع` | `a-vendre` | `en-venta` | `in-vendita` | `bikri-hetu` | `prodazha` |
| `rent` | `for-rent` | `للإيجار` | `a-louer` | `en-alquiler` | `in-affitto` | `kiraye-par` | `arenda` |
| `swap` | `for-swap` | `للتبادل` | `a-echanger` | `para-intercambio` | `da-scambiare` | `badalne-hetu` | `obmen` |

Every one of these reads as the phrase a person searches — "iPhone 13 for rent",
`آيفون 13 للإيجار`. That is the point of a modifier segment: it should be the query.

### City prefix

```ts
export const CITY_PREFIX: Record<Locale, string> = {
  en: 'in-',   ar: 'في-',  fr: 'a-',
  es: 'en-',   it: 'a-',   hi: 'me-',  ru: 'v-',
};
```

| Locale | Example | Reads as |
|---|---|---|
| `en` | `/for-rent/in-cairo` | "for rent in Cairo" |
| `ar` | `/للإيجار/في-القاهرة` | "للإيجار في القاهرة" |
| `fr` | `/a-louer/a-paris` | "à louer à Paris" |
| `es` | `/en-alquiler/en-madrid` | "en alquiler en Madrid" |
| `it` | `/in-affitto/a-milano` | "in affitto a Milano" |
| `ru` | `/arenda/v-moskve` | "аренда в Москве" |

Three things this buys at the cost of three characters:

1. **Determinism.** A city segment is identifiable without a database lookup, so
   the resolver never has to guess whether `zagreb` is a city or a model.
2. **No reserved-word conflict.** A brand called "Split" and the city Split can
   coexist, because one is `split` and the other is `in-split`.
3. **Readability.** The URL and the SERP breadcrumb both read as the search phrase.

A bare city slug (`/used/zagreb`) resolves and 308s to the prefixed form, so old
links and hand-typed URLs still work.

### Conditions

Values come from the `condition` enum already used across `listings` and mapped
in `meta-tags.service.ts` (`CONDITION_MAP`, `formatCondition`).

| Value | `en` slug | Notes |
|---|---|---|
| `new` | `new` | |
| `like_new` | `like-new` | |
| `excellent` | `excellent` | |
| `good` | `good` | |
| `fair` | `fair` | |
| `poor` | `poor` | |
| `for_parts` | `for-parts` | |
| — | `used` | **Alias group**: matches `like_new, excellent, good, fair` as one page. This is the highest-volume modifier ("iphone 13 used") and must be a first-class URL, not an OR of four. |

The `used` alias is defined once:

```ts
export const CONDITION_ALIASES: Record<string, string[]> = {
  used: ['like_new', 'excellent', 'good', 'fair'],
};
```

Individual condition pages (`/good`, `/fair`) are generated but almost never pass
the indexation gate — they exist for internal linking and direct navigation, not
for the index. `used`, `new`, and `for-parts` are the three that realistically
earn indexing.

Localized condition slugs live in `src/features/catalog-content/lib/modifier-vocab.ts`
and their display labels come from `messages/{locale}/catalogPages.json` so they are
translator-editable without a code change.

---

## 8. URL best-practices checklist

The rules this scheme is built to satisfy, and how each one is met. Use this as the
review checklist for any future URL change.

| Practice | How this scheme satisfies it |
|---|---|
| **Readable words, not IDs or codes** | Every segment is a slug derived from a human name. No UUIDs, no numeric node ids, no query parameters in an indexable URL. |
| **Hierarchy mirrors the content model** | Path depth *is* the catalog tier. A visitor and a crawler can both infer the parent by deleting the last segment — and that parent URL always exists. |
| **Hyphens, not underscores or camelCase** | Slugify emits `-` only. `iphone-13`, not `iphone_13` or `iPhone13`. |
| **Lowercase only** | Slugify lowercases. The resolver is case-insensitive on entry and 308s to the lowercase form, so `/Catalog/Electronics` does not become a duplicate. |
| **No trailing slash** | One form, enforced by Next's default `trailingSlash: false`. The other 308s. |
| **No file extensions** | None anywhere. |
| **Stable over time** | Slug changes write `catalog_slug_history` and 308 forever. A URL that ranked in 2026 still resolves in 2036. |
| **One canonical URL per piece of content** | A single `canonicalPath` per (node + modifiers + locale). Every other spelling — base slug under a localized locale, historical slug, out-of-order modifiers, bare city slug, wrong case — 308s to it. |
| **Query strings never indexable** | Filters and sort are client-side and always `noindex` with a canonical to the bare path. Anything worth indexing gets a path segment instead. |
| **Localized for the market** | Each locale has its own slug in its own script, so an Arabic search returns an Arabic URL. `hreflang` + `x-default` tie the seven together reciprocally. |
| **Modifier segments read as the search query** | `256gb`, `used`, `for-rent`, `in-cairo` — not `t=2`, `c=3`, `loc=41`. |
| **Faceted navigation cannot explode** | At most one attribute and two dimensions per indexable URL, from a declared list. Full cross-product would be 1.5 billion URLs; the policy caps it at ~10–15 real pages per model. See [15](15-facets-and-variants.md). |
| **Reasonable depth** | Indexable URLs are at most 8 segments after the locale (5-tier chain + 2 facet dimensions + prefix). Deeper permutations resolve but are never indexable. Tiers 1–3, which carry most traffic, are 2–4 segments. |
| **No duplicate content across paths** | A node is reachable at exactly one path. There is no `/brands/apple` *and* `/catalog/electronics/phones/apple` — the former 308s to the latter. |
| **Crawl budget protected** | Below-threshold permutations are never linked and never in the sitemap, so crawlers spend their budget on pages that can rank. |
| **Predictable for humans typing by hand** | `swibba.com/en/catalog/electronics/phones` is guessable. That is a real acquisition channel and a sign the hierarchy is honest. |

### Anti-patterns explicitly avoided

```
✗ /en/marketplace?cat=electronics&subcategory=8f3c-…   query params, no hierarchy
✗ /en/c/electronics                                     single-letter filler segment
✗ /en/category/12/subcategory/48/model/9021             opaque ids
✗ /en/electronics/phones/index.html                     file extension
✗ /en/Electronics/Phones/                               mixed case + trailing slash
✗ /en/electronics/phones/apple?condition=used&city=41   indexable content behind params
✗ /ar/catalog/electronics/phones                        English path serving Arabic content
✗ /en/catalog/used-iphone-13-zagreb-buy-cheap-best      keyword-stuffed flat slug
✗ /en/catalog/…/iphone-13/256gb/gold/used/in-zagreb    stacked facets, infinite space
✗ /en/catalog/…/3-series/127843-km                     per-value numeric facet
```

The last one is worth naming explicitly: a keyword-stuffed single slug looks
SEO-optimised and is the opposite. It has no parent, no siblings, no cluster, and
it reads as spam to both a person and a classifier. The hierarchy is what makes the
keywords credible.
