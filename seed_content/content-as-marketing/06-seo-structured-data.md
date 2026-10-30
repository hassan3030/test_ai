# 06 — SEO, Structured Data & Indexation

Programmatic pages are a double-edged tool. Done well they own the long tail; done
badly they get the whole domain classified as a doorway network. This file is the
set of rules that keeps us on the right side of that line.

---

## 1. The indexation gate

Every `/catalog/` URL resolves to exactly one of three states. The state is computed
server-side in `src/features/catalog-content/lib/indexation.ts` and consumed by
both `generateMetadata` and the sitemap — one source of truth, so the sitemap can
never advertise a `noindex` page.

```ts
export type IndexationState =
  | { kind: 'index' }
  | { kind: 'noindex'; canonicalTo: string; reason: NoindexReason }
  | { kind: 'notFound' };

export type NoindexReason =
  | 'content_missing' | 'content_draft' | 'content_thin'
  | 'fallback_locale' | 'fallback_ancestor'
  | 'below_supply_threshold' | 'paginated' | 'filtered';
```

### Decision table

| Condition | State | Robots | Canonical |
|---|---|---|---|
| Entity absent, or `status != published` | `notFound` | — | — |
| Catalog tier 1–5, published content for this locale, `word_count ≥ 250`, gate passed | **index** | `index, follow` | self |
| Modifier page, published content, **and** above its supply threshold | **index** | `index, follow` | self |
| Modifier page below its supply threshold | noindex | `noindex, follow` | nearest indexable ancestor |
| Facet shape not in `INDEXABLE_FACET_SHAPES` (two attributes, or ≥ 3 dimensions) | noindex | `noindex, follow` | nearest indexable ancestor |
| Any `query`-role facet param present | noindex | `noindex, follow` | bare path |
| Content missing or `status = draft` for this locale | noindex | `noindex, follow` | nearest indexable ancestor |
| Content served from the English fallback in a non-English locale | noindex | `noindex, follow` | the English URL |
| `?page ≥ 2` | noindex | `noindex, follow` | self (the paginated URL) |
| Any client filter query param present | noindex | `noindex, follow` | the bare path |

### Supply thresholds

```ts
export const SUPPLY_THRESHOLDS = {
  attribute:              3,   // /…/256gb
  condition:              3,   // /…/used
  listingType:            3,   // /…/for-rent
  city:                   5,   // /…/in-zagreb
  attributeAndCondition:  3,   // /…/256gb/used
  conditionAndCity:       3,   // /…/used/in-zagreb
  listingTypeAndCity:     3,   // /…/for-rent/in-cairo
  attributeAndCity:       5,   // /…/256gb/in-zagreb
} as const;
```

There is deliberately no `allThree` entry: three or more facet dimensions are
**never** indexable regardless of supply. The shape gate runs before the threshold
gate — see [15 §2](15-facets-and-variants.md).

Counts are the cached `listing_count` for that exact permutation, from
`catalog-aggregates:*`. Thresholds are deliberately low — a page with 3 real,
priced, photographed listings plus 400 words of specific editorial content is a
genuinely useful search result. They are constants in one file so they can be
tuned from GSC data without hunting through components.

### Demand override

A permutation below its supply threshold is promoted to **index** when
`subscriber_count ≥ 10`. Ten people asking for something is evidence the query has
real demand, and the page they get is honest about the absence and offers the
subscription. This is the one place where demand, not supply, earns indexation.

### Why this satisfies "always show content"

The user requirement was that a zero-supply page still shows useful content and
offers a notification subscription. It does: `noindex` affects **only** whether
search engines index the URL. The page returns `200`, renders the full editorial
stack, and shows the notify-me card. Users get everything; Google gets only the
pages worth its crawl budget.

---

## 2. Metadata generation

`app/[locale]/catalog/[...path]/metadata.ts`, following the structure already proven in
`app/[locale]/marketplace/categories/[subcat]/metadata.ts` — reuse its
`parseRobots`, `truncate`, `stripHtml`, `getOgLocale` helpers rather than writing
new ones, and extend `metaTagsService` for the shared pieces.

```ts
export async function generateMetadata({ params }): Promise<Metadata> {
  const { locale, path } = await params;
  const result = await resolveCatalogPath(path, locale);          // cache()d — free
  if (result.kind !== 'ok') return notFoundMetadata();

  const { resolved } = result;
  const content    = await getCatalogContent(resolved, locale);   // cache()d — free
  const indexation = await getIndexationState(resolved, locale);  // cache()d — free

  const title = pickTitle(resolved, content);      // meta_tags → content → dynamic
  const description = pickDescription(resolved, content);
  const canonical = indexation.kind === 'index'
    ? absoluteUrl(locale, resolved.canonicalPath)
    : absoluteUrl(locale, indexation.canonicalTo);

  return {
    title,
    description,
    keywords: content?.keywords?.join(', '),
    alternates: {
      canonical,
      languages: buildHreflang(resolved),      // see §3
    },
    openGraph: {
      title: content?.meta_title || title,
      description,
      url: canonical,
      siteName: 'Swibba',
      locale: localeConfig[locale].ogLocale,   // from src/i18n/config.ts
      type: 'website',
      images: ogImages(resolved, content),
    },
    twitter: {
      card: 'summary_large_image',
      title, description,
      images: ogImages(resolved, content).map(i => i.url),
      site: '@swibba', creator: '@swibba',
    },
    robots: indexation.kind === 'index'
      ? { index: true,  follow: true, googleBot: { index: true, follow: true,
          'max-image-preview': 'large', 'max-snippet': -1, 'max-video-preview': -1 } }
      : { index: false, follow: true },
  };
}
```

### Title formula

Priority order:

1. `meta_tags.title` when the entity has a published `meta_tags` row
2. `catalog_content_translations.meta_title`
3. Dynamic, per tier — always ≤ 60 chars including the suffix:

| Tier | Pattern | Example |
|---|---|---|
| category | `{Category} — Buy, Rent & Swap \| Swibba` | `Electronics — Buy, Rent & Swap \| Swibba` |
| subcategory | `{Subcategory} in {Category} \| Swibba` | `Phones in Electronics \| Swibba` |
| brand | `{Brand} {Subcategory} \| Swibba` | `Apple Phones \| Swibba` |
| series | `{Brand} {Series} — Prices & Listings \| Swibba` | `Apple iPhone — Prices & Listings \| Swibba` |
| model | `{Model} — Price & Listings \| Swibba` | `iPhone 13 — Price & Listings \| Swibba` |
| + condition | `{Condition} {Model} — Prices \| Swibba` | `Used iPhone 13 — Prices \| Swibba` |
| + city | `{Condition} {Model} in {City} \| Swibba` | `Used iPhone 13 in Zagreb \| Swibba` |
| + type | `{Model} for Rent in {City} \| Swibba` | `iPhone 13 for Rent in Cairo \| Swibba` |

The suffix is dropped before the node name is truncated — never truncate the thing
the page is about. `metaTagsService.truncate` already implements the right
behaviour for the length cap.

### Description formula

Dynamic fallback must contain a number, because a specific description earns
clicks. Pattern:

```
{N} {condition} {model} listings in {city} from {priceMin} to {priceMax}.
Compare prices, check condition, buy, rent or swap on Swibba.
```

With zero supply:

```
{Model} in {city}: typical second-hand prices, what to check before buying,
and free alerts when one is listed.
```

---

## 3. hreflang

Built from `resolved.localizedPaths`, using the `hreflang` values already declared
in `localeConfig` (`en-US, ar-SA, fr-FR, es-ES, it-IT, hi-IN, ru-RU`):

```ts
function buildHreflang(resolved: ResolvedCatalogPath): Record<string, string> {
  const out: Record<string, string> = {};
  for (const l of locales) {
    if (!resolved.localizedPaths[l]) continue;          // chain unresolvable there
    if (!isIndexableIn(resolved, l)) continue;          // don't advertise a noindex twin
    out[localeConfig[l].hreflang] = absoluteUrl(l, resolved.localizedPaths[l]);
  }
  out['x-default'] = absoluteUrl('en', resolved.localizedPaths.en);
  return out;
}
```

Rules that are easy to get wrong and matter:

- **Reciprocity.** Every URL listed must list every other, including itself. Because
  all seven are generated from one resolved chain, reciprocity is structural rather
  than something to remember.
- **Absolute URLs**, always, with the same scheme and host as the canonical.
- `x-default` → English.
- Do **not** list a locale whose page is `noindex` — pointing hreflang at a
  non-indexable twin wastes the signal.
- The same alternates go into the sitemap (§5). Google reads hreflang from either;
  having both is a consistency check, not redundancy.

---

## 4. Structured data

Injected in `app/[locale]/catalog/[...path]/layout.tsx` as a single
`<script type="application/ld+json">` containing a `@graph` array — one script tag,
not five, and cross-referenced by `@id` so entities are linked rather than repeated.

Escape `<` as `<` before injection, exactly as the existing category layout
already does:

```tsx
<script
  type="application/ld+json"
  dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c') }}
/>
```

### Per tier

| Tier | Types |
|---|---|
| category | `CollectionPage`, `BreadcrumbList`, `ItemList` (subcategories), `FAQPage`* |
| subcategory | `CollectionPage`, `BreadcrumbList`, `ItemList` (brands), `FAQPage`* |
| brand | `CollectionPage`, `BreadcrumbList`, `Brand`, `ItemList` (series), `FAQPage`* |
| series | `CollectionPage`, `BreadcrumbList`, `ItemList` (models), `FAQPage`* |
| model | `Product` + `AggregateOffer`†, `BreadcrumbList`, `FAQPage`* |
| modifier (condition / listing type / city) | `CollectionPage`, `BreadcrumbList`, `ItemList` (listings), `FAQPage`* |
| single-attribute facet on an `is_variant` attribute | `Product` + `AggregateOffer`†, `BreadcrumbList`, attribute as `additionalProperty` — semantically a variant |
| any other facet shape | `CollectionPage`, `BreadcrumbList`, `ItemList` — never `Product` |

\* only when `faqs.length ≥ 3`
† only when `offerCount ≥ 1`

`WebSite` + `SearchAction` stays where it already is, in the locale layout.

### Model tier example

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Product",
      "@id": "https://swibba.com/en/catalog/electronics/phones/apple/iphone/iphone-13#product",
      "name": "Apple iPhone 13",
      "description": "<tl_dr, plain text, ≤ 500 chars>",
      "category": "Electronics > Phones",
      "brand": { "@type": "Brand", "name": "Apple" },
      "model": "A2633",
      "releaseDate": "2021-09-24",
      "image": ["https://…/assets/<file-id>"],
      "additionalProperty": [
        { "@type": "PropertyValue", "name": "Storage", "value": "128 GB" }
      ],
      "offers": {
        "@type": "AggregateOffer",
        "priceCurrency": "EUR",
        "lowPrice": 320,
        "highPrice": 590,
        "offerCount": 24,
        "availability": "https://schema.org/InStock",
        "url": "https://swibba.com/en/catalog/electronics/phones/apple/iphone/iphone-13"
      }
    },
    { "@type": "BreadcrumbList", "itemListElement": [ … ] },
    { "@type": "FAQPage", "mainEntity": [
      { "@type": "Question", "name": "…",
        "acceptedAnswer": { "@type": "Answer", "text": "…" } } ] }
  ]
}
```

### Hard rules

1. **Never emit `Product`/`AggregateOffer` with `offerCount: 0`.** Google treats an
   offer-less Product with offers markup as a structured-data violation. Zero-supply
   model pages emit `CollectionPage` + `BreadcrumbList` + `FAQPage` instead.
2. **Every value must appear on the page.** `lowPrice`, `highPrice`, `offerCount`,
   specs, FAQ text — all rendered visibly. Markup that describes invisible content
   is a manual-action risk.
3. **No fabricated `LocalBusiness` or `Place` on geo pages.** Swibba does not have a
   storefront in Zagreb. Mention the city in prose and in `CollectionPage.name`;
   nothing more.
4. **No `AggregateRating` on catalog nodes.** Reviews attach to sellers, stores and
   products in this codebase — not to catalog entities — so there is nothing honest
   to aggregate at this level.
5. Reuse `CONDITION_MAP` and `AVAILABILITY_MAP` from
   `src/features/marketplace/services/meta-tags.service.ts` for schema.org enum
   URLs, and extend that service with the catalog builders rather than starting a
   parallel implementation.

### Where the code goes

```
src/features/marketplace/services/meta-tags.service.ts
  + buildCatalogJsonLd(resolved, content, aggregates, locale)
  + buildCatalogBreadcrumbJsonLd(resolved, locale)
  + buildItemListJsonLd(children, locale)
  + buildFaqJsonLd(faqs)
  + buildAggregateOfferJsonLd(aggregates)      // returns null when offerCount = 0
```

It is already a server-only singleton with the right mappings and truncation
helpers; growing it keeps one place responsible for "what Swibba tells search
engines".

---

## 5. Sitemaps

### Today

`app/sitemap.ts` returns one flat array: 9 static routes × 7 locales, plus every
published listing × 7 locales, with a comment noting the `-{id}` suffix
requirement. No `alternates`. No shards. At scale this exceeds the 50,000-URL /
50 MB limit and gets ignored.

### Target

A sitemap index via Next's `generateSitemaps()`, sharded and tagged:

```
/sitemap.xml                       index
/sitemap/static.xml
/sitemap/listings-0.xml … -N.xml   40k URLs per shard
/sitemap/catalog-categories.xml
/sitemap/catalog-subcategories.xml
/sitemap/catalog-brands.xml
/sitemap/catalog-series-0.xml …
/sitemap/catalog-models-0.xml …
/sitemap/catalog-modifiers-0.xml …
```

```ts
// app/sitemap.ts
export async function generateSitemaps() {
  return [
    { id: 'static' },
    ...(await listingShardIds()),
    { id: 'catalog-categories' },
    { id: 'catalog-subcategories' },
    { id: 'catalog-brands' },
    ...(await catalogShardIds('series')),
    ...(await catalogShardIds('models')),
    ...(await modifierShardIds()),
  ];
}

export default async function sitemap({ id }): Promise<MetadataRoute.Sitemap> {
  …
}
```

### Rules per entry

- **Only `IndexationState.kind === 'index'` URLs.** The shard builder calls the same
  `getIndexationState` the page uses. This is the single most important
  consistency guarantee in the whole feature.
- Every entry carries `alternates.languages` — one entry per node, seven language
  alternates, rather than seven separate entries. That is both correct and 7× smaller.
- `lastModified` from `catalog_content.date_updated`, falling back to the entity's
  `date_updated`.
- `changeFrequency` / `priority`:

| Shard | changeFrequency | priority |
|---|---|---|
| static | as today | as today |
| categories | `weekly` | 0.9 |
| subcategories | `weekly` | 0.8 |
| brands | `weekly` | 0.7 |
| series | `weekly` | 0.7 |
| models | `daily` | 0.8 |
| modifiers | `daily` | 0.6 |
| listings | `weekly` | 0.8 |

Models rank above series because a model page carries live price data that changes
daily and is where commercial intent lands.

- **Fix while here:** the listings shard must keep emitting `{slug}-{id}`. The
  existing comment in `app/sitemap.ts` records that a bare slug 404s.
- Wrap each shard in `unstable_cache` with tag `catalog-sitemap:{shard}` so a single
  entity edit refreshes one shard rather than the whole index.

### `robots.txt`

`app/robots.ts` needs three changes:

```ts
{
  userAgent: '*',
  allow: [
    '/',
    '/llms.txt',
    '/*/catalog/*?page=',        // pagination must stay crawlable
  ],
  disallow: [
    // …existing entries unchanged…
    '/*/catalog/*?',             // every other query-facet combination
  ],
}
sitemap: `${APP_URL}/sitemap.xml`,
```

Google honours the more specific `Allow`, so `?page=` stays crawlable while the
unbounded `query`-role facet space is never crawled at all.

This blanket `Disallow` is safe **only** because these URLs are brand new — nothing
has been indexed, so there is no equity to strand. For a URL that *was* previously
indexed, `noindex` **without** a `Disallow` is the correct tool: a blocked URL is one
Google can never see the `noindex` on, so it lingers in the index indefinitely.

Deliberately **not** disallowed:

- `/*/catalog/` itself — obviously
- `?page=` — those pages must be crawlable so the listings behind them are
  discoverable; they are `noindex, follow`, which is the correct tool. Blocking
  them in robots.txt would prevent Google from *seeing* the noindex, and would
  strand the links.
- Path-based facet URLs (`/…/iphone-13/256gb`) — they are the point. Only
  **query**-based facets are blocked.

---

## 6. Generative engine optimisation

`app/llms.txt/route.ts` currently lists 50 listings with their `tl_dr`. It becomes
the catalog map, which is far more useful to an answer engine than 50 arbitrary
listings:

```
# Swibba — AI Agent Directory
> {global_seo.default_meta_description}

## Catalog

### Electronics
Second-hand electronics across 7 subcategories, 340 live listings, €15–2,400.
https://swibba.com/en/catalog/electronics

#### Phones
{tl_dr}
https://swibba.com/en/catalog/electronics/phones

##### Apple iPhone 13
{tl_dr}
Live: 24 listings, €320–590, 7 cities.
https://swibba.com/en/catalog/electronics/phones/apple/iphone/iphone-13

## Top Listings
… existing section, unchanged …
```

- Depth-capped at the model tier, and only nodes in `index` state are listed.
- Ordered by `listing_count` so an agent reads the deepest supply first.
- Keeps the existing `text/plain` content type and
  `s-maxage=3600, stale-while-revalidate=86400` headers.
- `robots.ts` already grants `GPTBot`, `ChatGPT-User`, `Claude-Web`,
  `anthropic-ai`, `PerplexityBot` explicit access to it.

`tl_dr` doing double duty here — for AI answers and for the page's own summary —
is why the quality gate enforces that it be self-contained.

---

## 7. Anti-patterns this design forbids

| Anti-pattern | Guard |
|---|---|
| Thousands of near-identical pages | sibling-duplication check (gate #10) + supply thresholds |
| Full modifier permutation matrix | modifier URLs enumerated from real data, never generated combinatorially |
| Faceted-navigation index explosion (1.5 billion URLs) | `INDEXABLE_FACET_SHAPES`: max one attribute, max two dimensions, declared pairs only ([15](15-facets-and-variants.md)) |
| Per-value numeric facets (`/127843-km`) | numeric attributes must be `banded`; `seo_role: 'path'` on a numeric definition is a validation error |
| Facet pages claiming to be products | `Product` only on a single-attribute `is_variant` facet with `offerCount ≥ 1` |
| Empty pages behind internal links | the modifier cluster only links to gate-passing permutations, with real counts |
| Sitemap advertising `noindex` URLs | one shared `getIndexationState` for page and sitemap |
| Contradictory canonicals | one `canonicalPath` per resolved node; the existing `[subcat]/metadata.ts` bug is fixed as part of the migration |
| Markup describing invisible content | every structured-data value is rendered on the page |
| Fake offers on empty pages | `AggregateOffer` suppressed when `offerCount = 0` |
| Machine-translated duplicates across locales | native per-language generation + per-locale language check |
| Keyword-stuffed titles | 60-char cap, entity name first, one keyword phrase |
| Orphan deep pages | child-entity grid at every tier + sitemap shards + `llms.txt` tree |

---

## 8. Measurement

Baseline in Google Search Console **before** phase 1 ships.

| Signal | Where | Cadence |
|---|---|---|
| Indexed vs submitted per shard | GSC → Sitemaps | weekly |
| Coverage exclusions on `/catalog/` | GSC → Pages | weekly — a spike in "Duplicate, Google chose different canonical" means the facet policy is too loose. Tighten `INDEXABLE_FACET_SHAPES` or raise thresholds; never add shapes. |
| Impressions / clicks / position by page group | GSC → Performance, filtered to `/catalog/` | weekly |
| Non-English impressions share | GSC by country + page | monthly — the localized-slug bet |
| Rich-result eligibility | GSC → Enhancements (FAQ, Product, Breadcrumb) | weekly |
| Core Web Vitals on `/catalog/` | GSC → CWV, plus Lighthouse in CI | monthly |
| Crawl budget spent on `noindex` URLs | server logs by path pattern | monthly — if it is high, tighten thresholds |
| Alert subscriptions per node | `catalog_alerts` | weekly, in the dashboard demand report |

MS Clarity is already integrated and disclosed in the privacy policy (§7) and
terms (§11), so behavioural data on these pages needs no new consent work.
