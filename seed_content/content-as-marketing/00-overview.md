# 00 — Overview

## 1. The problem

Swibba's Directus backend already contains a complete five-tier product taxonomy
with translations for seven languages:

```
categories ──o2m──> subcategories ──o2m──> series ──o2m──> models
     │                     ▲                  ▲
     │ m2m                 │ subcategory_id   │
     └──> brands ──────────┴── brand_id ──────┘
                    (series joins brand + subcategory)

attribute_definitions ──m2m──> subcategories   (which specs apply where)
                      ──o2m──> models_attribute_values  (actual values per model)
```

None of it is reachable as content:

| Gap | Evidence |
|---|---|
| Only one catalog landing route exists | `app/[locale]/marketplace/categories/[subcat]/` — and despite the folder name its `metadata.ts` queries the **`categories`** collection. There is no subcategory, brand-in-category, series or model page. |
| That page is not server-rendered | `page.tsx` starts with `"use client"` and fetches Directus in `useEffect`. Crawlers get an empty shell; only `layout.tsx`'s `generateMetadata` + JSON-LD are server-side. |
| Nowhere to store editorial content | `categories_translations`, `subcategories_translations`, `series_translations`, `models_translations` all carry exactly `(name, description)`. Only `brands_translations` is richer (`tagline`, `about_us`, `mission`, `vision`, `meta_title`, `meta_description`). |
| Browse URLs are query strings | `/marketplace?cat=electronics`, `?subcategory=<uuid>`. No topical URL hierarchy for search engines to cluster. |
| Sitemap is thin and flat | `app/sitemap.ts` emits 9 static routes × 7 locales plus published `listings` × 7 locales. No catalog entities, no `hreflang` alternates, no sitemap index (breaks past 50k URLs). |
| Canonical tags contradict each other | In `app/[locale]/marketplace/categories/[subcat]/metadata.ts`, `buildMetadataFromDirectus` canonicalises to `/marketplace/categories/{slug}` while `buildMetadataDynamically` canonicalises to `/marketplace?cat={slug}`. |
| Nothing static or ISR'd | Only `app/[locale]/page.tsx` sets `revalidate = 60`. No `generateStaticParams` outside the locale layout. |

Net effect: a marketplace with a rich catalog is invisible for every
informational and long-tail commercial query about the things it sells.

## 2. The opportunity

Marketplace search demand is overwhelmingly long-tail and modifier-driven:

```
"iphone 13"                        ← head, brutal competition
"iphone 13 used"                   ← condition modifier
"iphone 13 used price"             ← intent modifier
"iphone 13 used in zagreb"         ← geo modifier  ← we can own this
"آيفون 13 مستعمل في القاهرة"        ← geo + language ← and this
```

Swibba has three assets that make this winnable:

1. **Structured catalog data** — a real entity graph, not a keyword list.
2. **Live inventory data** — real prices, real conditions, real cities, which is
   exactly the "unique, useful" signal Google rewards on programmatic pages.
3. **An AI pipeline already in production** — `app/api/seo-worker/route.ts`
   already generates `tl_dr` + `faqs` per listing translation via a Directus
   flow. The same pattern scales to the catalog.

## 3. Goals

| # | Goal | Measured by |
|---|---|---|
| G1 | Every catalog node has a crawlable, server-rendered landing page in 7 locales | `curl` of each tier returns `<h1>` + body copy in the HTML |
| G2 | Each page carries genuinely useful editorial content, not a product grid with a heading | body ≥ 250 words, 3–6 FAQs, buying guide, price guidance — enforced by the quality gate |
| G3 | Long-tail modifier queries (condition / city / listing type) have dedicated pages when there is real supply, and a useful page + demand capture when there is not | modifier pages live; alert subscriptions recorded |
| G4 | Localized URLs and content so each language ranks in its own market | localized slug per locale, `hreflang` + `x-default` complete |
| G5 | No thin-content or doorway-page exposure | only gate-passing URLs are indexable and in the sitemap |
| G6 | Content coverage scales without a content team | AI pipeline covers the whole catalog; humans only touch the review queue |

## 4. Success metrics

Baseline these in Google Search Console **before** phase 1 ships.

| Metric | Source | Target (90 days after phase 5) |
|---|---|---|
| Indexed `/catalog/` URLs | GSC Coverage | > 80% of gate-passing URLs |
| Organic impressions on catalog pages | GSC | primary growth metric |
| Organic clicks → listing detail | GSC + internal analytics | primary revenue proxy |
| Non-English organic impressions share | GSC by country | rising — proves the localized-slug bet |
| Average position for `{model} used {city}` sample set | GSC queries | tracked per launch market |
| Alert subscriptions created | `catalog_alerts` count | demand signal for merchandising |
| Alert → listing click-through | `notifications` + analytics | proves the notify-me loop closes |
| Core Web Vitals on `/catalog/` | Lighthouse / Clarity | LCP < 2.5s, CLS < 0.1, desktop |
| AI cost per published page | `ai_logs` via `writeGenerationLog` | tracked; ceiling set in `catalog_content_settings` |

## 5. Non-goals

Explicitly **out of scope** for this feature:

- **Rewriting the marketplace search/browse page.** `app/[locale]/marketplace/page.tsx`
  stays as the faceted search surface. `/catalog/` pages link into it.
- **Changing the product detail page.** `/[locale]/marketplace/{slug}-{id}` is
  unchanged; note the `-{id}` suffix is required by the route.
- **Product variants, inventory, pricing tiers.** The gaps listed in
  `backend/schema/CATALOG_ANALYSIS.md` §"What's Missing" are a separate track.
- **Paid acquisition, social, email campaigns.** This is organic + generative
  search only.
- **A blog or CMS for non-catalog content.** Only catalog-anchored content.
- **Migrating `listings` → `products`.** `listings` is the live collection
  (96 code references vs 6) and stays so.

## 6. Glossary

| Term | Meaning here |
|---|---|
| **Tier** | One of the five catalog levels: category, subcategory, brand, series, model |
| **Node** | A single entity at any tier, e.g. the `models` row for "iPhone 13" |
| **Chain** | The resolved ancestor path of a node, e.g. `electronics → phones → apple → iphone → iphone-13` |
| **Modifier** | A trailing URL segment that narrows a node: listing type, condition, or city |
| **Permutation** | A node + modifier combination, e.g. `iphone-13 + used + zagreb` |
| **Indexation gate** | The rule set deciding whether a URL is `INDEX`, `RENDER+NOINDEX`, or `404`. See [06](06-seo-structured-data.md) |
| **Quality gate** | The programmatic checks AI content must pass before `status: published`. See [03](03-content-pipeline.md) |
| **GEO** | Generative Engine Optimization — being cited by AI answer engines. Served by `tl_dr`, `faqs`, and `llms.txt` |
| **Market** | An ISO-3166-1 alpha-2 country whose supply/price/city data shapes the generated content |

## 7. Key confirmed decisions

| Decision | Choice | Rationale |
|---|---|---|
| URL scheme | Nested under a `/catalog/` prefix | One unambiguous hierarchy root; path depth identifies the tier; no collision with `/marketplace/[slug]` (product), `/marketplace/store/[slug]`, or top-level app routes |
| Content storage | New polymorphic `catalog_content` + `catalog_content_translations` | One pipeline, one flow, one admin UI, one gate — instead of five parallel copies; leaves the five existing catalog collections untouched |
| Content production | Directus Flow → OpenAI, on entity create/update, plus a backfill for existing entities, using live market + location context | Scales to the whole catalog × 7 languages; matches the pattern already proven by `app/api/seo-worker/route.ts` |
| Publishing | Auto-publish **only** on passing the quality gate; failures go to a review queue | Honours "dynamic and automatic" without exposing the site to a doorway-page penalty |
| Zero-supply pages | Always render content + a "notify me when available" subscription; keep them `noindex` until supply or demand justifies indexing | Users always get value; Google only gets pages worth indexing |
| Slugs | Localized per language, with `catalog_slug_history` for 301s | An Egyptian user searching Arabic must land on an Arabic URL and page |

## 8. Delivery shape

Six phases. Phases 1–2 deliver SEO value *before* any AI content exists, because
server-rendered pages with dynamic fallback metadata and real listings already
beat today's client-rendered shell.

```
Phase 0  Schema + permissions + scripts + this doc set
Phase 1  Resolver, /catalog/ routing, tiers 1–2, metadata, breadcrumbs, redirects
Phase 2  Tiers 3–5, key specs, price aggregates, AggregateOffer
Phase 3  AI content pipeline + review queue
Phase 4  Modifier pages + indexation gate + notify-me alerts
Phase 5  Sitemap index + hreflang + llms.txt + full revalidation wiring
Phase 6  Desktop polish, CWV, rich-results validation, measurement
```

Full breakdown: [10-tasks.md](10-tasks.md).
