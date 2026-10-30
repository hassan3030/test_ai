# Content as Marketing

> **Status**: Planned — not yet implemented
> **Owner**: Growth / Platform
> **Created**: 2026-08-18
> **Depends on**: existing catalog collections, `ai_settings` singleton, `notifications` collection, `listings`

Turn every node of Swibba's product catalog into a dedicated, server-rendered,
content-rich landing page in all 7 locales — so organic search becomes an
acquisition channel instead of an afterthought.

The catalog already holds the taxonomy. This feature adds the **content layer**,
the **URL layer**, and the **indexation layer** on top of it.

```
Today                                  After
─────                                  ─────
/en/marketplace?cat=electronics        /en/catalog/electronics
  ↳ client-rendered, empty HTML          ↳ server-rendered, editorial content
  ↳ no subcategory page                /en/catalog/electronics/phones
  ↳ no series page                     /en/catalog/electronics/phones/apple
  ↳ no model page                      /en/catalog/electronics/phones/apple/iphone
  ↳ no geo/condition page              /en/catalog/electronics/phones/apple/iphone/iphone-13
                                       /en/catalog/…/iphone-13/used/in-zagreb
                                       /ar/catalog/الكترونيات/هواتف/apple/iphone/iphone-13
```

---

## How to read this set

Read in order the first time. After that, jump to the file you need.

| # | File | What it answers |
|---|---|---|
| 00 | [Overview](00-overview.md) | Why, what success looks like, what is out of scope |
| 01 | [URL architecture](01-url-architecture.md) | The `/catalog/` scheme, the path resolver, localized slugs, redirects |
| 02 | [Data model](02-data-model.md) | Every new Directus collection and field, permissions, prod parity |
| 03 | [Content pipeline](03-content-pipeline.md) | How AI writes the content, the market context, the quality gate |
| 04 | [Rendering & caching](04-rendering-caching.md) | RSC + ISR, `generateStaticParams`, cache tags, revalidation |
| 05 | [Page composition](05-page-composition.md) | The section stack per tier, desktop layout spec |
| 06 | [SEO & structured data](06-seo-structured-data.md) | schema.org, hreflang, sitemap index, indexation policy |
| 07 | [Availability alerts](07-availability-alerts.md) | Notify-me subscriptions and the matching flow |
| 08 | [API routes](08-api-routes.md) | Every new/changed route handler and its contract |
| 09 | [Admin & dashboard](09-admin-dashboard.md) | Directus admin UX, the review queue, the demand report |
| 10 | [Tasks](10-tasks.md) | Phased, checkable task list with file paths |
| 11 | [Verification](11-verification.md) | How to prove each phase actually works |
| 12 | [Risks](12-risks.md) | What can go wrong, mitigations, rollback |
| 13 | [UI & motion](13-ui-and-motion.md) | The three-layer motion budget, visual system, RTL, performance guardrails |
| 14 | [Discovery](14-discovery.md) | Every surface inside Swibba that links into the catalog, and the three that are broken today |
| 15 | [Facets & variants](15-facets-and-variants.md) | Attribute-level URLs (`256gb`, `gold`, `diesel`), and the rules that stop 1.5 billion URLs |

---

## The five tiers, at a glance

| Tier | Directus collection | Example URL | Example query it targets |
|---|---|---|---|
| 1 | `categories` | `/en/catalog/electronics` | "buy used electronics online" |
| 2 | `subcategories` | `/en/catalog/electronics/phones` | "second hand phones marketplace" |
| 3 | `brands` | `/en/catalog/electronics/phones/apple` | "used apple phones" |
| 4 | `series` | `/en/catalog/electronics/phones/apple/iphone` | "iphone for sale used" |
| 5 | `models` | `/en/catalog/electronics/phones/apple/iphone/iphone-13` | "iphone 13 price used" |
| + | modifiers | `…/iphone-13/used/in-zagreb` | **"iphone 13 used in zagreb"** |
| + | attribute facets | `…/iphone-13/256gb/used` | **"iphone 13 256gb used"** |

---

## Non-negotiables

1. **Server-rendered.** Every `/catalog/` page ships its content in the initial HTML.
   The current category page fetches in `useEffect` and is invisible to crawlers;
   that is the single biggest thing this feature fixes.
2. **No thin pages in the index.** Pages always render for users, but only pages
   that pass the quality + demand gate are indexable and enter the sitemap.
   See [06](06-seo-structured-data.md).
3. **Facets never multiply.** At most one attribute and two facet dimensions per
   indexable URL, from a declared list. The full cross-product would be 1.5 billion
   URLs; the policy caps it at roughly 10–15 real pages per model.
   See [15](15-facets-and-variants.md).
4. **All 7 locales, natively.** Content is written per language, not translated
   from English, and URLs are localized — so an Arabic query in Egypt lands on
   the Arabic page. See [01](01-url-architecture.md) and [03](03-content-pipeline.md).
5. **Reuse what exists.** `getAiSettings`, `runReasoning`, `writeGenerationLog`,
   `getLocalizedContent`, `metaTagsService`, the `notifications` collection, the
   `/api/revalidate` webhook. New code only where nothing exists.
6. **Prod parity is a deliverable.** Directus schema, public-role permissions and
   flows live in the Directus database and do **not** travel with a code deploy.
   Every change ships with a re-runnable script. See [02](02-data-model.md).

---

## Quick links into the existing codebase

| Concern | Where it lives today |
|---|---|
| Catalog schema dumps | `backend/schema/*.json`, `backend/schema/CATALOG_ANALYSIS.md` |
| Locale list + hreflang map | `src/i18n/config.ts` |
| Locale ↔ Directus lang code | `src/features/catalog/utils/localization.ts` |
| Locale negotiation middleware | `proxy.ts` (Next 16 renamed `middleware.ts`) |
| SEO metadata service | `src/features/marketplace/services/meta-tags.service.ts` |
| Worked metadata example | `app/[locale]/marketplace/categories/[subcat]/metadata.ts` |
| Existing AI GEO worker | `app/api/seo-worker/route.ts` |
| AI settings + prompts | `src/lib/ai/config.ts`, `src/lib/ai/prompts.ts` |
| Cache purge webhook | `app/api/revalidate/route.ts` |
| Sitemap / robots / llms.txt | `app/sitemap.ts`, `app/robots.ts`, `app/llms.txt/route.ts` |
