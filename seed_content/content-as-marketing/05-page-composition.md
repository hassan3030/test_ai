# 05 — Page Composition

One shared page shell, thirteen sections, toggled per tier. Desktop is the primary
optimisation target, as requested — but the layout is fluid from 360 px up because
mobile traffic still converts.

---

## 1. Section stack

| # | Section | Cat | Sub | Brand | Series | Model | Modifier |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| 1 | Breadcrumb | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Hero (H1, lede, image, live stats, CTAs) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 3 | Child-entity grid | ✓ | ✓ | ✓ | ✓ | — | — |
| 4 | Live listings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 5 | Editorial body + TOC rail | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 6 | Buying guide | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 7 | Key specs table | — | — | — | ✓ | ✓ | ✓ |
| 8 | Price guidance | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 9 | Comparison strip | — | — | — | ✓ | ✓ | — |
| 10 | FAQ accordion | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 11 | Modifier link cluster | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 12 | Related links | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 13 | Notify-me card | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Sections 3–13 render **only when they have real content**. An empty section is
worse than a missing one: it is the visual signature of a thin programmatic page.

### Order changes when supply is zero

When `listing_count = 0`, the stack reorders so the page still answers the visit:

```
1 Breadcrumb → 2 Hero → 13 Notify-me (promoted) → 5 Editorial → 6 Buying guide
→ 8 Price guidance → 7 Key specs → 10 FAQ → 3 Child grid → 11 Modifiers → 12 Related
```

Section 4 is replaced by an empty state that names the situation plainly
("No live listings for this right now") and hands the visitor the two useful
actions: subscribe for alerts, or list one themselves.

---

## 2. Per-section spec

### 1 · Breadcrumb

New component: `src/shared/components/Breadcrumb.tsx`. Only
`src/features/support/components/SupportBreadcrumb.tsx` exists today and it is
support-specific.

```tsx
interface BreadcrumbProps {
  items: Array<{ label: string; href?: string }>;   // last item has no href
  className?: string;
}
```

- Server component, zero JS.
- Semantic `<nav aria-label>` + `<ol>`.
- Full localized chain: `Home / Catalog / Electronics / Phones / Apple / iPhone / iPhone 13`.
- On narrow viewports, collapse the middle with an ellipsis but keep every item in
  the DOM (crawlers and screen readers get the whole trail).
- RTL: the separator flips via logical properties, not a conditional.
- Emits `BreadcrumbList` JSON-LD — see [06](06-seo-structured-data.md).

### 2 · Hero

```
┌────────────────────────────────────────────────────────────────┐
│  [image 480×360]   H1: iPhone 13                               │
│                    lede paragraph, 60–120 words                │
│                                                                │
│                    ┌──────┬──────────┬────────┬─────────────┐  │
│                    │  24  │ €320–590 │   7    │  Used, New  │  │
│                    │ live │  price   │ cities │ conditions  │  │
│                    └──────┴──────────┴────────┴─────────────┘  │
│                    [ Browse 24 listings ] [ Sell yours ]       │
│                    [ Notify me ]                               │
└────────────────────────────────────────────────────────────────┘
```

- Exactly one `<h1>` per page, from `catalog_content_translations.h1`, falling back
  to the localized entity name.
- Image: `hero_image` → entity `image`/`logo` → the highest-quality image among
  the node's listings → a generated gradient placard with the node name. `priority`
  on this image only; explicit `width`/`height`.
- Stat strip numbers come from the cached aggregates. Every number is a link:
  price range → the grid sorted by price, cities → the modifier cluster,
  conditions → the condition modifier pages.
- "Sell yours" deep-links into `/{locale}/dashboard/listings/new` with the catalog
  chain prefilled — the highest-intent conversion on the page for a seller.

### 3 · Child-entity grid

The internal-link engine. Without this, deep nodes are orphans.

| Parent tier | Children shown | Label source |
|---|---|---|
| category | subcategories, then brands in that category | `categories.brand_label` |
| subcategory | brands with series in this subcategory | `categories.brand_label` |
| brand | series for this brand in this subcategory | `categories.series_label` |
| series | models | `categories.model_label` |

`categories` already carries `show_series`, `show_models`, `brand_label`,
`series_label`, `model_label`. **Honour those flags** — a category that sets
`show_models = false` must not render a model grid, and the visible heading must
use the configured label rather than a hardcoded "Models".

Card: image, localized name, live listing count, price-from. Sorted by listing
count descending so the crawlable links point at the pages most worth crawling.
Cap at 24 with a "see all" link to the parent's full child list.

### 4 · Live listings

- Server-rendered first page of 24. See [04 §6](04-rendering-caching.md).
- Reuses `ProductsGrid` and `BusinessProductCardsSection` from
  `@/features/marketplace/components`, fed by props.
- Header shows the count and a sort control; the filter rail (condition, price,
  city, listing type) is client-side and **never** changes the URL path — path-based
  narrowing is what modifier pages are for.
- "View all N listings" links into `app/[locale]/marketplace` with the node's
  filters prefilled.

### 5 · Editorial body + TOC rail

```
┌─ xl and up ────────────────────────────────────────────────────┐
│ ┌────────────────────────────────┐  ┌────────────────────────┐ │
│ │ col-span-8                     │  │ col-span-4  (sticky)   │ │
│ │  h2 What is …                  │  │  On this page          │ │
│ │  p …                           │  │   · What is …          │ │
│ │  h2 How to choose              │  │   · How to choose      │ │
│ │  ul li …                       │  │   · Prices             │ │
│ │  h2 Prices in {market}         │  │   · FAQ                │ │
│ └────────────────────────────────┘  │  ─────────────────     │ │
│                                     │  Price range €320–590  │ │
│                                     │  24 live listings      │ │
│                                     │  [ Notify me ]         │ │
│                                     └────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

- Below `xl` the rail moves inline above the body as a collapsed TOC.
- HTML comes from `catalog_content_translations.body`, already sanitised at write
  time (see [03 §10](03-content-pipeline.md)). Sanitise again on render with
  `dompurify` — defence in depth, cheap.
- Allowed tags on render: `p h2 h3 ul ol li strong em`. Anything else is stripped.
- The TOC is derived server-side from the `<h2>`/`<h3>` in the body, with ids
  injected during sanitisation. Zero client JS; anchors are plain links.
- Typography: `max-w-[68ch]` measure, `text-[17px]/[1.7]` body — long-form reading,
  not UI density.
- When content came from a fallback step (see [03 §8](03-content-pipeline.md)),
  render a small, honest notice above the body ("This section describes
  {parent name}") rather than passing parent copy off as this node's.

### 6 · Buying guide

Same restricted HTML, rendered as a distinct card with its own `<h2>`. This is the
section that earns featured snippets, so it keeps a scannable list structure.

### 7 · Key specs table

Series and model tiers. Two columns on desktop, one on mobile.

- Source: `catalog_content_translations.key_specs`, itself seeded from
  `models_attribute_values` joined to `attribute_definitions` (+ translations for
  the label).
- Only definitions with `is_filter = true` or present in `knownSpecs` are shown, so
  the table stays decision-relevant rather than exhaustive.
- Units come from the attribute definition, not from the AI text.
- Each spec row whose definition has `is_filter = true` links into the marketplace
  search with that facet applied.

### 8 · Price guidance

- Live block: min / median / max, currency, sample size, "as of" timestamp — all
  from the cached aggregates.
- Editorial block: `price_guidance` HTML explaining what moves the price here.
- Condition breakdown bar (`conditionMix`) with each segment linking to that
  condition's modifier page.
- When `listing_count = 0`: show catalogue anchors (`msrp`, `base_price`) clearly
  labelled as reference prices, and say there is no live supply. Never render a
  fabricated range.

### 9 · Comparison strip

Series and model tiers. Horizontal scroller of sibling models with name, image,
key differentiating spec, live price-from, and a link. Fed by
`comparison_notes` for the prose and by the sibling query for the data.

Practical value: it is the strongest internal link between sibling model pages,
which is exactly the graph Google needs to understand a series.

### 10 · FAQ accordion

- 3–6 items from `catalog_content_translations.faqs`.
- **All answers present in the HTML**, collapsed with `<details>`/`<summary>` so
  they are readable with JS off and indexable regardless.
- Emits `FAQPage` JSON-LD.

### 11 · Modifier link cluster

The section that turns one node page into a long-tail cluster.

```
┌─ iPhone 13 by condition ──────────────────────────────────────┐
│  Used iPhone 13 (18)   New iPhone 13 (4)   For parts (2)      │
├─ iPhone 13 by city ───────────────────────────────────────────┤
│  Zagreb (7)  Cairo (5)  Split (3)  Rijeka (3)  Osijek (2)     │
├─ iPhone 13 used, by city ─────────────────────────────────────┤
│  Used in Zagreb (6)  Used in Cairo (4)  Used in Split (3)     │
├─ Other ways to get one ───────────────────────────────────────┤
│  iPhone 13 for rent (2)   iPhone 13 for swap (1)              │
└───────────────────────────────────────────────────────────────┘
```

Rules:

- Only links to permutations that pass the indexation gate. Below-threshold
  permutations still *resolve* if someone types them, but are not linked — so the
  crawlable graph stays clean.
- Counts are shown, and they are real. A link with a count is a promise; an empty
  page behind a link is how a site earns a doorway-page classification.
- Ordered by count descending, capped at 12 per group.
- On a modifier page, the cluster inverts: it links back to the bare node, sideways
  to nearby cities (by lat/long from `geo_locations`), and to the same city at the
  parent tier.

### 12 · Related links

Parent node, sibling nodes at the same tier, popular brands in the category,
and the marketplace search entry point. Plain server-rendered links.

### 13 · Notify-me card

Always rendered. Promoted directly under the hero when `listing_count = 0`.

```
┌───────────────────────────────────────────────────────────┐
│  Nothing available right now                              │
│  Tell us what you're after and we'll message you the       │
│  moment a matching iPhone 13 is listed in Zagreb.          │
│                                                            │
│  Condition [ Used ▾ ]  Max price [ 450  ] [ EUR ▾ ]        │
│  ( signed out: email field )                               │
│  [ Notify me ]                                             │
│  3 other people are waiting for this.                      │
└───────────────────────────────────────────────────────────┘
```

- Pre-fills condition / city / listing type from the current page's modifiers.
- Signed in → one click, no email field. Signed out → email + double opt-in.
- The social-proof line uses `subscriber_count` and only appears above 3, to avoid
  advertising that nobody wants the thing.
- Full behaviour in [07-availability-alerts.md](07-availability-alerts.md).

---

## 3. Desktop layout spec

Tailwind v4 is already configured (`@tailwindcss/postcss`). No new breakpoints —
use the defaults plus the existing container conventions.

| Token | Value |
|---|---|
| Page container | `mx-auto w-full max-w-[1440px] px-4 sm:px-6 lg:px-8` |
| Grid | `grid grid-cols-4 md:grid-cols-8 xl:grid-cols-12 gap-6 xl:gap-8` |
| Content / rail split | content `xl:col-span-8`, rail `xl:col-span-4 xl:sticky xl:top-24 self-start` |
| Section rhythm | `py-10 lg:py-14`, `space-y-10 lg:space-y-16` between sections |
| Child grid columns | `grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6` |
| Listings grid columns | inherit `ProductsGrid`'s existing responsive columns |
| Body measure | `max-w-[68ch]` |
| Body type | `text-[17px] leading-[1.7]` |
| H1 | `text-3xl lg:text-5xl font-semibold tracking-tight` |
| H2 | `text-xl lg:text-2xl font-semibold` |
| Sticky sub-nav | appears after the hero scrolls out, `h-14`, links to section anchors |

Desktop-specific behaviours:

- **Sticky rail** from `xl` only. Below that it would eat the viewport.
- **Sticky sub-nav** with the section anchors, shown once the hero leaves the
  viewport. Implemented with a CSS sticky element and an `IntersectionObserver`-free
  approach where possible; if JS is needed, it is a 20-line client component.
- **Hover affordances** on child cards and comparison items (lift + border) — these
  are pure CSS and don't exist on touch.
- **Two-up comparison** in the comparison strip at `2xl`, single-row scroll below.
- **Wide tables** (`key_specs`) get `overflow-x-auto` on their own wrapper so the
  page body never scrolls horizontally.

### RTL

`localeConfig[locale].direction` already exists in `src/i18n/config.ts` and the
`[locale]` layout sets `dir`. Requirements for these sections:

- Use logical properties throughout: `ps-*`/`pe-*`, `ms-*`/`me-*`, `text-start`,
  `border-s`, never `pl-*`/`text-left`.
- Breadcrumb separators, comparison scrollers and the stat strip all mirror.
- Numbers and prices stay LTR inside RTL text — wrap them in
  `<span dir="ltr" class="inline-block">`.
- Arabic body copy needs slightly more leading: `[dir=rtl]:leading-[1.85]`.

### Accessibility

- One `<h1>`; `<h2>` for every section; no heading level skipped.
- `<section aria-labelledby>` on each section, pointing at its heading id.
- FAQ uses native `<details>`/`<summary>` — keyboard and screen reader support for
  free.
- Every interactive element has a visible focus ring; tap targets ≥ 44 px.
- Stat strip numbers get `aria-label` text spelling out what they mean
  ("24 live listings").
- Contrast ≥ 4.5:1 in both themes (`next-themes` is already wired).

---

## 4. i18n

### Use a new namespace, not the existing `catalog` one

`messages/{locale}/catalog.json` **already exists** and is loaded by both the
`marketplace` and `dashboard` namespace groups in `src/i18n/config.ts`. Its root
key is `catalog` and it already owns `catalog.categories`, `catalog.subcategories`,
`catalog.brands`, `catalog.series` for the dashboard catalog managers. Adding
landing-page copy there would collide.

So this feature gets its own namespace: **`catalogPages`**.

Three changes in `src/i18n/config.ts`:

```ts
export const allNamespaces = [
  …,
  'catalogPages',                    // ← add
] as const;

export const NAMESPACE_GROUPS = {
  …,
  /** Catalog landing pages (/catalog/**) */
  catalogPages: [
    'catalogPages', 'marketplace', 'categories', 'brands',
    'product', 'listItem', 'favorites', 'currencies',
  ],
};
```

Then create `messages/{en,ar,fr,es,it,hi,ru}/catalogPages.json` — all **seven**,
because `t()` returns the raw key when a translation is missing, so a key present
in `en` and absent in `ru` renders literally as `catalogPages.hero.browseListings`
on the Russian page. Add a CI check that diffs the key sets across locales.

### Key groups

```
catalogPages.breadcrumb.{home,catalog}
catalogPages.hero.{browseListings,sellYours,notifyMe,liveListings,priceRange,cities,conditions}
catalogPages.children.{seeAll,listingsCount,priceFrom}
catalogPages.listings.{title,empty,emptyBody,viewAll,sortBy}
catalogPages.editorial.{onThisPage,aboutParentNotice,languageNotice}
catalogPages.guide.title
catalogPages.specs.{title,label,value}
catalogPages.price.{title,min,median,max,sampleSize,asOf,noSupply,referencePrice}
catalogPages.compare.{title,vs}
catalogPages.faq.title
catalogPages.modifiers.{byCondition,byCity,byConditionAndCity,otherWays,byAttribute}
catalogPages.facets.{title,clearAll,showMore,bandUnder,bandOver,bandBetween}
catalogPages.related.{title,parent,siblings,popularBrands,searchAll}
catalogPages.alerts.{title,titleEmpty,body,condition,maxPrice,currency,email,submit,
                     waiting,successSignedIn,successGuest,alreadySubscribed,manage,
                     confirmSent,confirmed,unsubscribed}
catalogPages.conditions.{new,like_new,excellent,good,fair,poor,for_parts,used}
catalogPages.listingTypes.{sell,rent,swap}
catalogPages.notifications.{alertSubject,alertMessage,alertFinal}
```

Two separations that matter:

- Condition and listing-type **labels** come from these keys; their **URL slugs**
  come from `src/features/catalog-content/lib/modifier-vocab.ts`. A copy tweak must
  never change a live URL.
- `catalogPages.notifications.*` is rendered server-side in the *subscriber's*
  stored locale by the alert matcher — see [07 §3](07-availability-alerts.md) — so
  those keys are read outside any React render and must not rely on request context.

---

## 5. Component inventory

```
src/features/catalog-content/components/
  CatalogPageShell.tsx          server  — grid, sticky rail, sub-nav, noindex banner in dev
  CatalogHero.tsx               server
  CatalogStatStrip.tsx          server
  CatalogChildGrid.tsx          server
  CatalogChildCard.tsx          server
  CatalogEditorial.tsx          server  — sanitise + inject heading ids
  CatalogToc.tsx                server
  CatalogBuyingGuide.tsx        server
  CatalogSpecsTable.tsx         server
  CatalogPriceGuidance.tsx      server
  CatalogConditionBar.tsx       server
  CatalogComparisonStrip.tsx    server
  CatalogFaq.tsx                server  — <details>/<summary>
  CatalogModifierCluster.tsx    server
  CatalogRelatedLinks.tsx       server
  CatalogListingsSection.tsx    client  — receives initialListings as props
  CatalogAlertCard.tsx          client  — the notify-me form
  CatalogStickyNav.tsx          client  — small, optional
src/shared/components/
  Breadcrumb.tsx                server  — generic, reusable outside this feature
```

Fifteen of eighteen are server components, which is why the page adds essentially
no JavaScript over what the marketplace already ships.
