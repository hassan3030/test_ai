# 04 — Rendering & Caching

## 1. The rule that matters most

**Every `/catalog/` page ships its content in the initial HTML.**

Today's category page does not. `app/[locale]/marketplace/categories/[subcat]/page.tsx`
opens with `"use client"` and fetches Directus inside `useEffect`, so a crawler
receives a spinner. Only `layout.tsx`'s `generateMetadata` and JSON-LD are
server-rendered — a page with perfect meta tags and no body.

Everything in this file exists to make that impossible on `/catalog/`.

### The concrete pattern

```tsx
// app/[locale]/catalog/[...path]/page.tsx        ← SERVER component, no "use client"
export const revalidate = 3600;
export const dynamicParams = true;

export default async function CatalogPage({ params, searchParams }: Props) {
  const { locale, path } = await params;

  const result = await resolveCatalogPath(path, locale as Locale);
  if (result.kind === 'notFound') notFound();
  if (result.kind === 'redirect') permanentRedirect(`/${locale}${result.to}`);

  const { resolved } = result;

  // All data fetched HERE, on the server, in parallel.
  const [content, children, listings, aggregates, indexation] = await Promise.all([
    getCatalogContent(resolved, locale),
    getChildEntities(resolved, locale),
    getListingsPage(resolved, { page: 1, limit: 24 }),
    getAggregates(resolved),
    getIndexationState(resolved, locale),
  ]);

  return (
    <CatalogPageShell resolved={resolved} indexation={indexation}>
      {/* server-rendered sections */}
      <CatalogHero … />
      <CatalogEditorial html={content.body} />
      {/* client component, but data arrives as PROPS → still SSR'd into HTML */}
      <CatalogListingsSection
        initialListings={listings.items}
        initialTotal={listings.total}
        resolved={serializeResolved(resolved)}
      />
      <CatalogFaq faqs={content.faqs} />
    </CatalogPageShell>
  );
}
```

The subtlety worth stating explicitly: **client components are server-rendered in
the App Router.** A `"use client"` component still emits HTML on the first
request. What kills SEO is not `"use client"` — it is fetching *inside* the
component. So the interactive filter grid stays a client component, and it
receives `initialListings` as props. Its first paint is in the HTML; only
subsequent filter changes hit the network.

Rule for reviewers: **no `useEffect` fetch anywhere under `app/[locale]/catalog/`.**

## 2. Rendering strategy per route

| Route | Strategy | Directives |
|---|---|---|
| `app/[locale]/catalog/page.tsx` (hub) | ISR, pre-rendered for all 7 locales | `revalidate = 3600`, `generateStaticParams` returns the locale list |
| `app/[locale]/catalog/[...path]/page.tsx` | ISR, partially pre-rendered | `revalidate = 3600`, `dynamicParams = true`, scoped `generateStaticParams` |
| `app/[locale]/catalog/[...path]/opengraph-image.tsx` | ISR | `revalidate = 86400` |

`dynamicParams = true` is the load-bearing setting: any path not in
`generateStaticParams` is rendered on first request and then cached, rather than
404ing. That is what makes a 5000-model catalog viable without pre-rendering
35,000 pages.

## 3. `generateStaticParams` — scoped, never exhaustive

Pre-rendering every model × 7 locales × modifier permutation is not an option.
Pre-render only what earns it:

```ts
export async function generateStaticParams() {
  const [categories, subcategories, hotNodes] = await Promise.all([
    getAllPublishedCategories(),          // tens
    getAllPublishedSubcategories(),       // low hundreds
    getTopNodesByDemand(200),             // brands + series + models
  ]);

  const paths: string[][] = [];
  for (const c of categories) paths.push([c.slug]);
  for (const s of subcategories) paths.push([s.categorySlug, s.slug]);
  for (const n of hotNodes) paths.push(n.chainSlugs);
  return paths;                            // locale comes from the parent segment
}
```

- `getTopNodesByDemand` orders by `catalog_content.listing_count`, then
  `subscriber_count`, then `models.views`-equivalent signals — the nodes most
  likely to be crawled and clicked.
- Modifier permutations are **never** pre-rendered. They are discovered through
  the sitemap and internal links, then ISR-cached on first crawl.
- `app/[locale]/layout.tsx` already has `generateStaticParams` for locales; the
  catch-all's params compose with it, so the effective count is
  `paths.length × 7`. Keep `paths.length` under ~500 so a cold build stays fast.

Build-time cost check: 500 paths × 7 locales = 3,500 pre-rendered pages. At the
current data volume that is acceptable; if the build gets slow, drop
`getTopNodesByDemand` to categories+subcategories only and let everything else be
on-demand. Nothing about correctness depends on pre-rendering.

## 4. Data layer

`src/features/catalog-content/services/catalog-page.service.ts` — server-only.

```ts
import 'server-only';
import { cache } from 'react';
import { unstable_cache } from 'next/cache';
import { createAdminClient } from '@/core/api/directus';
```

Two layers of caching, doing different jobs:

| Layer | Scope | Purpose |
|---|---|---|
| `cache()` (React) | one request | de-duplicates the same read across `generateMetadata`, `layout`, and `page` — which all need the resolved chain. The existing `metadata.ts` files already use this pattern (`fetchCategoryForMetadata = cache(...)`). |
| `unstable_cache()` | across requests, tagged | the actual persistent cache, purged surgically by the revalidate webhook |

```ts
export const getCatalogContent = cache(async (resolved, locale) =>
  unstable_cache(
    () => fetchCatalogContent(resolved.entity, locale),
    ['catalog-content', resolved.entity.tier, resolved.entity.id, locale],
    { tags: [`catalog-content:${resolved.entity.tier}:${resolved.entity.id}`], revalidate: 3600 },
  )(),
);
```

### Cache tag scheme

| Tag | Busted when | Consumed by |
|---|---|---|
| `catalog:{tier}:{id}` | the entity row or its translations change | resolver, chain reads, child grids |
| `catalog:categories:all` | any category changes | hub page, resolver's category map |
| `catalog:subcategories:all` | any subcategory changes | resolver's subcategory map |
| `catalog-content:{tier}:{id}` | `catalog_content` / `_translations` for that entity | page body, metadata |
| `catalog-aggregates:{tier}:{id}:{market}` | any listing in that node changes | hero stats, price guidance, indexation gate, AI context bundle |
| `catalog-listings:{tier}:{id}` | any listing in that node changes | the server-rendered first page of the grid |
| `geo:all` | any `geo_locations` change | modifier vocabulary in the resolver |
| `geo:{cityId}` | that city changes | geo page content, city blurb |
| `catalog-sitemap:{shard}` | anything that changes a sitemap shard | `app/sitemap.ts` shards |
| `global_seo` | already exists | site name / default description |

Tag names are produced by one helper so they can never drift between producer and
consumer:

```ts
// src/features/catalog-content/lib/cache-tags.ts
export const catalogTags = {
  entity:     (t: CatalogTier, id: string) => `catalog:${t}:${id}`,
  content:    (t: CatalogTier, id: string) => `catalog-content:${t}:${id}`,
  aggregates: (t: CatalogTier, id: string, market = 'global') =>
                `catalog-aggregates:${t}:${id}:${market}`,
  listings:   (t: CatalogTier, id: string) => `catalog-listings:${t}:${id}`,
  city:       (id: string) => `geo:${id}`,
  sitemap:    (shard: string) => `catalog-sitemap:${shard}`,
} as const;
```

## 5. Extending `/api/revalidate`

`app/api/revalidate/route.ts` currently handles exactly two cases —
`global_seo` and `listings | listings_translations` — and falls back to
`revalidatePath('/', 'layout')` for everything else, which nukes the whole app's
layout cache. That fallback is why catalog changes must be mapped explicitly.

### New mapping

```ts
const CATALOG_TIER_BY_COLLECTION: Record<string, CatalogTier> = {
  categories: 'category',       categories_translations: 'category',
  subcategories: 'subcategory', subcategories_translations: 'subcategory',
  brands: 'brand',              brands_translations: 'brand',
  series: 'series',             series_translations: 'series',
  models: 'model',              models_translations: 'model',
};
```

| Incoming collection | Tags revalidated |
|---|---|
| any of the five tiers or their `_translations` | `catalog:{tier}:{id}`, `catalog-content:{tier}:{id}`, the tier's `…:all` map tag where one exists, and `catalog-sitemap:{tier}` |
| `catalog_content`, `catalog_content_translations` | `catalog-content:{entity_type}:{entity_id}`, `catalog-sitemap:{entity_type}` |
| `geo_locations`, `geo_locations_translations` | `geo:all`, `geo:{id}`, `catalog-sitemap:modifiers` |
| `listings`, `listings_translations` | existing behaviour **plus** the five chain tags for that listing (see below) |
| `catalog_alerts` | `catalog-content:{entity_type}:{entity_id}` (subscriber count feeds the demand signal) |
| `global_seo` | unchanged |
| anything else | keep the existing fallback |

### The listings fan-out

A listing changing price or status changes the aggregates, the grid, and possibly
the indexation state of up to five nodes plus a city. So on a `listings` webhook
the route reads the listing's chain columns and busts all of them:

```ts
const { category_id, subcategory_id, brand_id, series_id, model_id,
        location_city, location_country } = listing;

const pairs: Array<[CatalogTier, string | null]> = [
  ['category', category_id], ['subcategory', subcategory_id],
  ['brand', brand_id], ['series', series_id], ['model', model_id],
];

for (const [tier, id] of pairs) {
  if (!id) continue;
  revalidateTag(catalogTags.aggregates(tier, id));
  revalidateTag(catalogTags.listings(tier, id));
}
const cityId = await lookupGeoLocationId(location_country, location_city);
if (cityId) revalidateTag(catalogTags.city(cityId));
```

Note the Directus webhook payload for `items.update` carries `keys[]`, not the
row — so the route fetches the listing's chain columns with the admin token before
fanning out. One extra read per webhook, which is fine: this runs on write, not
on read.

The existing normalisation comment in `app/api/seo-worker/route.ts` documents the
`key` vs `keys` inconsistency; reuse the same defensive extraction here.

### Directus flow wiring

`scripts/marketing-content/06-build-flows.mjs` also creates/updates the
revalidation flow so it covers the new collections:

```
name:    Marketing Content / Revalidate
trigger: items.create | items.update | items.delete
collections: categories, categories_translations,
             subcategories, subcategories_translations,
             brands, brands_translations,
             series, series_translations,
             models, models_translations,
             catalog_content, catalog_content_translations,
             geo_locations, geo_locations_translations
action:  POST {APP_URL}/api/revalidate
         Authorization: Bearer {REVALIDATE_SECRET}
         body: { collection, keys, key }
```

The existing `listings` revalidation flow keeps working; only the handler behind
it grows the fan-out.

## 6. Listings on the page

Each `/catalog/` page shows real inventory. Two concerns pull in opposite directions:
crawlers need it in the HTML, users need it interactive.

```
┌─ server ──────────────────────────────────────────────┐
│ getListingsPage(resolved, { page: 1, limit: 24 })     │
│   → Directus read, filtered by the node's tier column │
│   → unstable_cache tag catalog-listings:{tier}:{id}   │
└──────────────────┬────────────────────────────────────┘
                   │ props
┌──────────────────▼────────────────────────────────────┐
│ <CatalogListingsSection>  ("use client")              │
│   initialListings / initialTotal / resolved            │
│   • first paint comes from props → in the HTML         │
│   • filter or page change → /api/marketplace/… fetch   │
└───────────────────────────────────────────────────────┘
```

- Reuse `ProductsGrid` and `BusinessProductCardsSection` from
  `@/features/marketplace/components` rather than building new cards — they
  already handle the individual/business split, currency, and favourites.
- Reuse `SearchFilters` from `src/features/marketplace/types/index.ts` for the
  filter shape; it already has `categoryId`, `subcategoryId`, `brandId`,
  `condition[]`, `location_city`, `location_country`, `transactionType`,
  `sortBy`, `page`, `limit`.
- The node's identity maps straight onto those filters, so "browse all" links into
  `app/[locale]/marketplace` with prefilled state and no new API surface.
- Pagination beyond page 1 is client-side against the existing marketplace API.
  Page 1 is always the server-rendered one, which is the only page that needs to
  be crawlable (deeper pages are `noindex` — see
  [06-seo-structured-data.md](06-seo-structured-data.md)).

## 7. Freshness contract

| Data | Max staleness | Mechanism |
|---|---|---|
| Editorial content | until the next write | tag-purged on `catalog_content` change |
| Chain / names / slugs | until the next write | tag-purged on entity change |
| Listing grid, counts, price range | 1 hour, or immediately on any listing write | `revalidate: 3600` + listings fan-out |
| Indexation state | 1 hour | derived from the aggregates cache |
| Sitemap shards | 1 hour, or immediately on relevant writes | shard tags |
| `llms.txt` | 1 hour | existing `s-maxage=3600` header |

An hour of lag on a price range is acceptable because the page also renders the
live grid from the same cached read — user and gate always see a consistent
number, never a contradictory one.

## 8. Performance budget

| Metric | Target | How |
|---|---|---|
| Server render time (cache miss) | < 400 ms | all node reads in one `Promise.all`; resolver maps pre-cached |
| Server render time (cache hit) | < 30 ms | ISR |
| Directus reads per cold render | ≤ 6 | chain (1, from cached maps) + content (1) + children (1) + listings (1) + aggregates (2) |
| LCP (desktop) | < 2.5 s | hero image `priority`, explicit dimensions, no client fetch before first paint |
| CLS | < 0.1 | every image and card slot has fixed intrinsic size |
| JS shipped | no increase over the marketplace page | reuse existing components; editorial sections are server-only |

The editorial body, FAQ, specs table and breadcrumb are all **server components** —
they add zero JavaScript. The only client JS on the page is the listings grid, the
FAQ accordion's disclosure state, and the notify-me form.

## 9. Environment

No new environment variables. The pipeline uses what already exists:

```
NEXT_PUBLIC_APP_URL        canonical/OG/sitemap base
NEXT_PUBLIC_DIRECTUS_URL   Directus base
DIRECTUS_ADMIN_TOKEN       server-side reads + writes
REVALIDATE_SECRET          webhook auth (falls back to DIRECTUS_ADMIN_TOKEN)
OPENAI_API_KEY             content generation
```

> Secret-rotation note: `directus.env` and `.env.local` were previously committed
> to git history, so all of these are considered compromised until rotated. This
> feature does not add exposure, but it does add another consumer of
> `REVALIDATE_SECRET` — rotate it and the Directus flow headers together.
