# 10 — Tasks

> **Status, 2026-08-20.** Phase 0 is applied and verified on dev. Phase 1's code
> is written. The three data seeds — the part that turns an empty schema into a
> catalog you can actually browse — are written and **run**:
>
> | Delivered | Result on dev |
> |---|---|
> | `04-backfill-slugs.mjs` | 380 base slugs canonicalised, **36,399 localized slugs** across 5 tiers × 7 languages. `08-check-slug-collisions.mjs`: **467 → 0 problems** |
> | `05-seed-geo-locations.mjs` | **556 cities** covering all 86 countries in `COUNTRY_DEFAULT_LOCALE`, resolved from OpenStreetMap, + 3,892 localized names |
> | `11-seed-attribute-option-values.mjs` | 61 attributes classified (`18 path / 7 banded / 30 query / 6 none`), **191 option values** + 1,337 translations |
> | Phase 3 pipeline | `build-context`, `quality-gate` (17 checks), `content-fallback`, `generate.service`, `POST /api/catalog-content/generate`, `12-backfill-content.mjs` |
>
> Still open: the editorial backfill run itself, Phase 2 tiers 3–5 rendering,
> Phase 4 alerts, Phase 5 sitemaps, Phase 6 polish.

Seven phases. Each is independently shippable and independently valuable — phases
1–2 improve SEO before a single word of AI content exists, because a
server-rendered page with dynamic metadata and real listings already beats today's
client-rendered shell.

Verification for every phase is in [11-verification.md](11-verification.md).

---

## Phase 0 — Foundations

**Goal**: schema, permissions and scripts in place on dev, snapshotted for prod.
**Ships nothing user-visible.**

- [x] `docs/content-as-marketing/**` — this doc set
- [x] `scripts/marketing-content/01-apply-schema.mjs` — idempotent create/patch of:
  - [x] `catalog_content` (+ `entity_label`) and `catalog_content_translations`
  - [x] `geo_locations` and `geo_locations_translations`
  - [x] `catalog_alerts`
  - [x] `catalog_slug_history`
  - [x] `slug` on all five `*_translations`
  - [x] `catalog_content_settings` singleton (26 fields: generation, refresh triggers, quality gate, indexation). Deliberately NOT on `ai_settings`.
  - [x] indexes and unique constraints per [02](02-data-model.md)
- [x] `scripts/marketing-content/02-apply-permissions.mjs` — public / user / manager
      policies, field allowlists, no wildcards
- [x] `scripts/marketing-content/05-seed-geo-locations.mjs` *(03 was taken by
      `03-seed-settings.mjs`)* — **556 cities covering all 86 countries that map
      to one of the seven locales**, resolved from
      OpenStreetMap rather than hand-typed: real coordinates, real population,
      real localized names in up to 7 languages. `_geo-cities.mjs` holds only the
      editorial "which cities" decision; the answers are cached in
      `geo-cities-resolved.json` so the seed replays without hitting a public API
- [x] `attribute_option_values` (+ translations) and the three new
      `attribute_definitions` fields (`seo_role`, `url_priority`, `option_values`) —
      see [15 §4](15-facets-and-variants.md)
- [x] `scripts/marketing-content/11-seed-attribute-option-values.mjs` — 191 option
      values from the `options` JSON, each with a `raw_variants` normalisation set
      assembled from generated spellings **plus values actually present** in
      `listings_attribute_values` and `models_attribute_values`. Unmatched real
      values are **reported, never auto-created**, and split by whether the
      attribute can produce a URL at all. Note: 19,472 of 19,485
      `models_attribute_values` rows have `attribute_definitions_id = NULL` with
      the spec key in `value` — it is a free-text spec sheet, usable as content
      context and unusable as a facet source
- [x] Classify `seo_role` per attribute — `_facet-policy.mjs`, with a reason on
      every line. 18 `path`, 7 `banded`, 30 `query`, 6 `none`. The two-per-
      subcategory cap is enforced at resolve time by `url_priority`, because
      `seo_role` is global and the cap is per-subcategory; `08-check` now fails
      on a **tie** at the cut rather than on the count
- [x] `scripts/marketing-content/08-check-slug-collisions.mjs` — CI audit. **0 problems**
- [ ] `scripts/marketing-content/11-sweep-orphans.mjs`
- [ ] Directus admin polish per [09 §1](09-admin-dashboard.md): field groups,
      display templates, restricted WYSIWYG toolbars, `catalog_alerts` hidden
- [x] `docs/content-as-marketing/directus-snapshot/` — collections, fields,
      relations, permissions, flows
- [ ] Add `check-slug-collisions` to CI

**Exit**: all scripts re-runnable with no diff on a second run; snapshot committed.

---

## Phase 1 — Routing + tiers 1–2

**Goal**: `/catalog/` exists, category and subcategory pages are server-rendered in all
7 locales, old routes redirect.

**Resolver + primitives**
- [ ] `src/features/catalog-content/types/index.ts` — `CatalogTier`,
      `CatalogChainNode`, `CatalogModifiers`, `ResolvedCatalogPath`, `ResolveResult`
- [ ] `src/features/catalog-content/lib/slugify.ts` — Unicode-aware, no transliteration
- [ ] `src/features/catalog-content/lib/reserved-slugs.ts`
- [ ] `src/features/catalog-content/lib/modifier-vocab.ts` — localized listing-type
      and condition slugs + `CONDITION_ALIASES`
- [ ] `src/features/catalog-content/lib/cache-tags.ts`
- [ ] `src/features/catalog-content/lib/resolve-path.ts` — the algorithm in
      [01 §3](01-url-architecture.md)
- [ ] `src/features/catalog-content/lib/indexation.ts` — the gate, tiers 1–2 only
      for now
- [ ] `src/features/catalog-content/services/catalog-page.service.ts` — chain,
      children, listings, aggregates; `cache()` + `unstable_cache` + tags

**Routes**
- [ ] `app/[locale]/catalog/page.tsx` — hub, all categories
- [ ] `app/[locale]/catalog/[...path]/page.tsx` — server component, `revalidate = 3600`,
      `dynamicParams = true`, scoped `generateStaticParams`
- [ ] `app/[locale]/catalog/[...path]/layout.tsx` — JSON-LD graph
- [ ] `app/[locale]/catalog/[...path]/metadata.ts` — `generateMetadata`, canonical,
      hreflang, robots from the gate

**Components**
- [ ] `src/shared/components/Breadcrumb.tsx`
- [ ] `CatalogPageShell`, `CatalogHero`, `CatalogStatStrip`, `CatalogChildGrid`,
      `CatalogChildCard`, `CatalogEditorial`, `CatalogToc`, `CatalogRelatedLinks`
- [ ] `CatalogListingsSection` (client, props-fed) wrapping the existing
      `ProductsGrid` / `BusinessProductCardsSection`

**i18n**
- [ ] `src/i18n/config.ts` — add `catalogPages` to `allNamespaces` and a
      `catalogPages` entry to `NAMESPACE_GROUPS`. **Do not reuse the existing
      `catalog` namespace** — it is already owned by the dashboard catalog managers
      and has colliding keys (`catalog.categories`, `catalog.brands`, …)
- [ ] `messages/{en,ar,fr,es,it,hi,ru}/catalogPages.json` — key groups per
      [05 §4](05-page-composition.md), all seven in sync
- [ ] CI check diffing locale key sets

**Discovery — fix the three broken internal-link surfaces** (see [14](14-discovery.md))
- [ ] `Header/CategoriesBar.tsx` — read live categories from the cached map; **delete
      the hardcoded `categoriesName` array (line 62)**; link to `/catalog/`
- [ ] `home/CategoriesSection/CategoryCard.tsx` + `BentoCategoryCard.tsx` —
      `/marketplace?cat={slug}` → `/{locale}/catalog/{localizedSlug}`
- [ ] `home/CategoriesSection/CategoriesSection.tsx` + `CategoriesBento.tsx` —
      hub links → `/{locale}/catalog`
- [ ] `home/BrandsSection/BrandCard.tsx` — `router.push()` → a real `<Link href>`
      (today brand pages get **no crawlable internal link** from the home page)
- [ ] `layout/Footer/useFooterConfig.ts` — add Browse + Popular cities columns
- [ ] ESLint `no-restricted-syntax` banning `marketplace?cat=` and
      `marketplace/categories/` in new code

**Migration**
- [ ] `app/[locale]/marketplace/categories/page.tsx` → `permanentRedirect('/{locale}/catalog')`
- [ ] `app/[locale]/marketplace/categories/[subcat]/*` → redirect; delete the
      contradictory canonical builders with the page body
- [x] `scripts/marketing-content/04-backfill-slugs.mjs` — all five tiers, not just
      two: 380 base slugs canonicalised and **36,399 localized slugs** written.
      Does **not** write `catalog_slug_history` by default, because no catalog
      slug has ever been a live URL, so there is nothing to redirect from
      (`--history` for any later re-run)
- [ ] Localized slug editing + validation in
      `app/api/dashboard/catalog/{categories,subcategories}/[id]/route.ts`

**Exit**: `curl /en/catalog/electronics` and `curl /ar/catalog/الكترونيات` both return an `<h1>`
and body copy in the HTML; old category URLs 308 into `/catalog/`.

---

## Phase 2 — Tiers 3–5

**Goal**: brand, series and model pages, with live price aggregates and specs.

- [ ] Extend `resolve-path.ts` to brand → series → model, with the scoping rules
      (brand via `brands_categories` **and** a matching `series`; series via
      `brand_id` + `subcategory_id`; model via `series_id`)
- [ ] Extend `indexation.ts` to tiers 3–5
- [ ] Aggregate reads: count, min/median/max price, condition mix, listing-type mix,
      top cities — one grouped query per node, tagged `catalog-aggregates:*`
- [ ] `key_specs` assembly from `models_attribute_values` + `attribute_definitions`
      (+ translations for labels)
- [ ] `CatalogSpecsTable`, `CatalogPriceGuidance`, `CatalogConditionBar`,
      `CatalogComparisonStrip`, `CatalogBuyingGuide`, `CatalogFaq`
- [ ] Honour `categories.show_series` / `show_models` / `brand_label` /
      `series_label` / `model_label` in the child grid and headings
- [ ] `meta-tags.service.ts`: `buildCatalogJsonLd`, `buildCatalogBreadcrumbJsonLd`,
      `buildItemListJsonLd`, `buildFaqJsonLd`, `buildAggregateOfferJsonLd`
      (returns `null` at `offerCount = 0`)
- [ ] `app/[locale]/marketplace/brand/[slug]/*` → redirect into `/catalog/`, with the
      orphan-brand fallback
- [ ] Header mega-menu panel — server-rendered links, live data, keyboard accessible;
      `MobileMenu.tsx` gets the same tree as an accordion
- [ ] Product detail page: breadcrumb with the full localized chain + a
      "More {model} on Swibba" block
- [ ] `meta-tags.service.ts` — `generateBreadcrumbJsonLd` must emit `/catalog/`
      paths, **not** the current `?category={id}` / `?subcategory={id}` query URLs
      (product pages are currently declaring non-indexable breadcrumb parents)
- [ ] Extend `backfill-slugs.mjs` to brands, series, models
- [ ] Localized slug editing in the remaining three catalog write routes
- [ ] `catalog_slug_history` writes in all five write routes

**Exit**: all five tiers render server-side in all 7 locales; a model page emits
`Product` + `AggregateOffer` only when it has offers.

---

## Phase 3 — AI content pipeline

**Goal**: content generated automatically for new entities and backfilled for
existing ones, with a review queue for gate failures.

**Prompt + settings**
- [x] `DEFAULT_CATALOG_CONTENT_PROMPT` in `src/lib/ai/prompts.ts`
- [ ] `catalog_content_settings.system_prompt` + `catalog_content_settings.batch_size` in
      `AiSettings` / `DEFAULT_AI_SETTINGS` (`src/lib/ai/config.ts`)
- [x] Seeded by `03-seed-settings.mjs` into `catalog_content_settings.system_prompt`
      — the runtime reads Directus, not the TS constant
- [ ] Surface the prompt read-only in `app/[locale]/dashboard/settings/ai/`,
      enforced in route + form + policy

**Generator**
- [x] `src/features/catalog-content/lib/build-context.ts` — the context bundle
- [x] `src/features/catalog-content/lib/quality-gate.ts` — 18 checks, `gate_report`
      (check 12 split: prompt/payload leakage blocks, page self-reference warns)
- [x] `src/features/catalog-content/lib/content-fallback.ts` — the 4-step ladder
- [x] `src/features/catalog-content/services/generate.service.ts` — English pass,
      native per-locale passes, gate, upsert, slug promotion, log, revalidate
- [x] `app/api/catalog-content/generate/route.ts` — plus a `GET` readiness probe
- [x] `max_output_tokens` = 6000 from `catalog_content_settings`, JSON parse
      failure retried once and logged with the response length

**Automation**
- [ ] `scripts/marketing-content/06-build-flows.mjs` — the generate flow and the
      extended revalidate flow
- [x] `scripts/marketing-content/12-backfill-content.mjs` — resumable, prioritised
      by live listings then subscribers then tier, with a cost estimate from the
      configured price table before any spend
- [ ] `app/api/cron/catalog-content-refresh/route.ts` — aggregates always, content
      bounded, plus the sweeps

**Discovery**
- [ ] `app/api/search/suggestions/route.ts` — add a BROWSE group of catalog nodes
      above the listing results
- [ ] Home page trending catalog rail (top nodes + permutations by demand)
- [ ] Marketplace: banner when active filters match an indexable node
- [ ] Store page: "this store sells in these categories"

**Governance**
- [ ] `app/[locale]/dashboard/moderation/catalog-content/page.tsx` — Review queue,
      Coverage, Pipeline tabs
- [ ] Content-status column in the five catalog list views

**Exit**: creating a model in Directus produces published content in 7 languages
within minutes; failures appear in the review queue with a readable `gate_report`.

---

## Phase 4 — Modifier pages + alerts

**Goal**: the long tail, and demand capture where supply is missing.

**Modifiers & facets** (see [15](15-facets-and-variants.md))
- [ ] Modifier parsing in `resolve-path.ts`: canonical order
      `attribute → condition → listingType → city`, one-per-kind,
      out-of-order → 308, missing city prefix → 308
- [ ] `src/features/catalog-content/lib/facet-policy.ts` —
      `INDEXABLE_FACET_SHAPES`; a second attribute parses but forces `noindex`
- [ ] `src/features/catalog-content/lib/facet-bands.ts` — numeric bands
- [ ] Attribute matching scoped to the node's subcategory via
      `subcategories_attribute_definitions`, `seo_role in ('path','banded')`
- [ ] Listing filter + count on `listings_attribute_values` using the **full
      normalised value set** for the chosen option row
- [ ] `catalog_content_translations.facet_notes` (JSON keyed by facet slug),
      generated **once per node** covering all its facet values — never one AI call
      per facet URL
- [ ] `robots.ts`: `Disallow: /*/catalog/*?` + `Allow: /*/catalog/*?page=`
- [ ] `check-slug-collisions.mjs` extended to option slugs vs condition and
      listing-type tokens
- [ ] `SUPPLY_THRESHOLDS` + the `subscriber_count ≥ 10` demand override in
      `indexation.ts`
- [ ] Per-permutation aggregate reads
- [ ] `CatalogModifierCluster` — links only to gate-passing permutations, with real counts
- [ ] Modifier-aware titles, descriptions and JSON-LD
- [ ] Zero-supply page ordering per [05 §1](05-page-composition.md)

**Alerts**
- [ ] `app/api/catalog-content/alerts/route.ts` (POST, GET)
- [ ] `app/api/catalog-content/alerts/[id]/route.ts` (PATCH, DELETE)
- [ ] `app/api/catalog-content/alerts/confirm/route.ts`
- [ ] `app/api/catalog-content/alerts/unsubscribe/route.ts` — GET confirms, POST acts
- [ ] `app/api/catalog-content/alerts/match/route.ts` — chain match, alias expansion,
      throttle, self-exclusion, 200-recipient cap
- [ ] `scripts/marketing-content/06-build-flows.mjs` — `listings` → match, with the
      status-transition guard
- [ ] `CatalogAlertCard` (client) with page-prefilled defaults
- [ ] Guest double opt-in email + the token manage page
- [ ] Alerts tab on `app/[locale]/dashboard/favorites`
- [ ] Demand tab in the moderation dashboard + CSV export
- [ ] Rate limits per [07 §2](07-availability-alerts.md)
- [ ] Zero-results state on marketplace search: catalog page + create-alert +
      broader modifier page
- [ ] Listing create/edit: "see the N other {model} listings and their prices" link
- [ ] Privacy-policy addition covering alert emails and retention — Directus CMS,
      all 7 languages, re-applied on prod

**Exit**: `/…/iphone-13/used/in-zagreb` renders content + subscribe at zero supply and
is `noindex`; publishing 5 matching listings flips it to indexable; subscribing then
publishing a match produces a `notifications` row in the subscriber's locale.

---

## Phase 5 — Sitemaps, hreflang, cache wiring

**Goal**: everything discoverable, nothing over-purged.

- [ ] Rewrite `app/sitemap.ts` as a sharded index via `generateSitemaps()`
- [ ] Shards: static, listings (40k each, keeping `{slug}-{id}`), categories,
      subcategories, brands, series, models, modifiers
- [ ] `alternates.languages` on every entry
- [ ] Shard reads filtered through the **shared** `getIndexationState`
- [ ] Shard-level cache tags `catalog-sitemap:{shard}`
- [ ] `app/robots.ts` — `/catalog/` filter-param disallows; `?page=` left crawlable
- [ ] `app/llms.txt/route.ts` — `## Catalog` tree with `tl_dr`, index-state only
- [ ] `app/api/revalidate/route.ts` — full collection→tag map, listings five-tag
      fan-out, city tag, logging for unmapped collections
- [ ] Crawl-depth audit — nothing indexable deeper than 4 clicks from home
- [ ] Orphan check — every `index`-state URL has ≥ 1 internal link
- [ ] Submit the new sitemap index in Google Search Console

**Exit**: every sitemap URL returns `200` with `index, follow`; no `noindex` URL
appears in any shard.

---

## Phase 6 — Desktop polish, motion, performance, measurement

Motion direction is **confident but disciplined** — full spec in
[13-ui-and-motion.md](13-ui-and-motion.md). Nothing above the fold animates.

- [ ] Layer 1: `cm-reveal` / `cm-reveal-group` CSS scroll-driven reveals on
      sections 5–13, behind `@supports (animation-timeline: view())` and
      `prefers-reduced-motion: no-preference`
- [ ] Layer 1: card hover lift + image zoom, scroll-snap comparison strip,
      native `<details>` FAQ height transition
- [ ] Layer 2: View Transitions — `viewTransitionName` keyed on entity id so the
      clicked child card's image and title morph into the destination hero and H1;
      `catalog-breadcrumb` stays anchored across navigation
- [ ] Layer 3: framer-motion on the four components that need it only —
      listings `AnimatePresence`, alert-card success morph, mobile filter drawer,
      sticky-nav `layoutId` underline. All read `useReducedMotion()`
- [ ] Sticky content rail from `xl`, sticky sub-nav after the hero
- [ ] `2xl` child-grid and comparison-strip density
- [ ] RTL pass on all 13 sections with `ar`; logical properties only
- [ ] `[dir=rtl]` leading adjustment; prices wrapped `dir="ltr"`
- [ ] Accessibility pass: heading order, `aria-labelledby` per section, focus rings,
      44 px targets, contrast in both themes
- [ ] `app/[locale]/catalog/[...path]/opengraph-image.tsx` — node name, tier chain, live
      price range, count
- [ ] Lighthouse desktop on one URL per tier; LCP < 2.5 s, CLS < 0.1
- [ ] `scripts/marketing-content/13-validate-jsonld.mjs` in CI
- [ ] GSC: baseline recorded, page-group filters saved, Enhancements watched
- [ ] Dashboard coverage reconciliation check wired to alert on sitemap mismatch

**Exit**: all targets in [11 §7](11-verification.md) met.

---

## Phase 7 — Deferred / nice-to-have

Explicitly out of the initial delivery, listed so they are not forgotten:

- Content diff viewer between `content_version`s
- Per-market content variants beyond the `primary_market` field the schema already
  supports (e.g. distinct EG and HR copy for the same model)
- Nearby-city links using `geo_locations` lat/long
- Region and country tiers between city and global
- `ItemList` markup for the listings grid itself (currently only child entities)
- Automated internal-link auditing (orphan detection, click-depth report)
- A/B testing title and description formulas against GSC CTR

---

## Cross-phase engineering rules

Non-negotiable for every PR in this feature:

1. **No `useEffect` data fetching under `app/[locale]/catalog/`.** Data is fetched on the
   server and passed as props. This is the whole point of the feature.
2. **One source of truth for indexation.** Page, metadata and sitemap all call
   `getIndexationState`. Never inline a robots decision.
3. **One source of truth for cache tags.** Always `catalogTags.*`; never a string
   literal.
4. **Reuse before writing.** `getAiSettings`, `runReasoning`, `writeGenerationLog`,
   `getLocalizedContent`, `getLanguageCode`, `metaTagsService`, `ProductsGrid`,
   `SearchFilters`, the `notifications` collection.
5. **All 7 locale files, every time.** A missing key renders as the raw key.
6. **Sanitise HTML on write and on render.**
7. **Never log `catalog_alerts.email`.**
8. **Every Directus change ships as a re-runnable script plus a snapshot update.**
   Schema, permissions and flows are DB state and do not travel with a deploy.
9. **Pause the Marketing Content flows around any bulk write.** `Revalidate` and
   `Generate` are armed on all five catalog collections *and* all five
   translation collections, so a 36,470-row slug backfill is 36,470 revalidate
   webhooks and 36,470 generate triggers — measured at ~193 ms per row, about two
   hours of wall clock spent entirely on flow dispatch, and a real AI bill the
   moment `generation_enabled` is on. Use `_flow-guard.mjs`; it prints its own
   recovery command because a SIGKILL leaves the flows paused.
