# 14 — Discovery: How Users Reach the Content Pages

Search engines are only one entrance. If the only way to a catalog page is Google,
the pages are a bolt-on rather than part of the product — and Google notices that
too, because internal links are how it discovers and weights pages in the first
place.

This file covers every surface inside Swibba that must link into `/catalog/`.

---

## 1. The problem today

Category links are currently split **three ways**, which fragments link equity
across two URL forms for the same content and passes none from the third:

| Where | Links to | Problem |
|---|---|---|
| `src/shared/components/layout/Header/CategoriesBar.tsx:170` | `/{locale}/marketplace/categories/{slug}` | The category list is a **hardcoded array** (`categoriesName`, line 62), not read from Directus. New categories never appear. |
| `src/shared/components/home/CategoriesSection/CategoryCard.tsx:88` | `/marketplace?cat={slug}` | Query string. Not a crawlable destination, passes no equity, and is a different URL for the same content as the row above. |
| `src/shared/components/home/CategoriesSection/BentoCategoryCard.tsx:90` | `/marketplace?cat={slug}` | Same. |
| `src/shared/components/home/CategoriesSection/CategoriesSection.tsx:175` | `/marketplace/categories` | Third form — the hub. |
| `src/shared/components/home/BrandsSection/BrandCard.tsx:46` | `router.push('/{locale}/marketplace/brand/{slug}')` | Client-side `push` rather than an `<a>`, so it is **invisible to crawlers**. |
| `src/shared/components/layout/Footer/useFooterConfig.ts` | — | **No category links at all.** The footer is the single cheapest sitewide internal-linking surface and it is unused. |

Fixing these is not optional polish. Two of them are the reason the current
category pages have weak internal link signal, and the `router.push` on brand cards
means brand pages receive no crawlable internal links from the home page whatsoever.

---

## 2. Entry-point map

Every surface, what it links to, and why it matters.

```
                          ┌──────────────────────┐
                          │   Google / AI answer │
                          └──────────┬───────────┘
                                     ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  ┌──────────────┐
│   Header    │  │  Home page  │  │  Catalog hub         │  │   Footer     │
│ mega-menu   │─▶│  category   │─▶│  /{locale}/catalog   │◀─│  top cats +  │
│ + search    │  │  + brand    │  │  (the index page)    │  │  top cities  │
└──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  └──────────────┘
       │                │                     │
       ▼                ▼                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     /catalog/{category}/…/{model}                     │
│                   the five tiers + modifier pages                     │
└───────▲──────────────────▲───────────────▲──────────────▲────────────┘
        │                  │               │              │
┌───────┴──────┐  ┌────────┴───────┐  ┌────┴─────┐  ┌─────┴────────┐
│   Product    │  │  Marketplace   │  │  Store / │  │  Empty states│
│   detail     │  │  search page   │  │  brand   │  │  & no-results│
│ (breadcrumb) │  │ (facet → page) │  │  pages   │  │              │
└──────────────┘  └────────────────┘  └──────────┘  └──────────────┘
```

---

## 3. Header — a real mega-menu

**Change**: `CategoriesBar.tsx` stops using its hardcoded array and reads the live
catalog. It becomes the primary browse affordance on desktop.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Electronics ▾  Automotive ▾  Fashion ▾  Home ▾  Sports ▾  Real Estate ▾  │
└─────┬────────────────────────────────────────────────────────────────────┘
      ▼ (hover / focus, desktop)
┌──────────────────────────────────────────────────────────────────────────┐
│  Phones           Laptops          Audio           Cameras               │
│  ├ Apple          ├ Apple          ├ Sony          ├ Canon               │
│  ├ Samsung        ├ Dell           ├ Bose          ├ Nikon               │
│  └ Xiaomi         └ Lenovo         └ JBL           └ Sony                │
│                                                                          │
│  Popular right now              ─────────────────────────────────────    │
│  iPhone 13 · Galaxy S22 · MacBook Air M2 · AirPods Pro                   │
│                                                                          │
│  [ Browse all Electronics → ]        342 listings · from €12             │
└──────────────────────────────────────────────────────────────────────────┘
```

Requirements:

- **Server-rendered links.** The menu markup is in the HTML — real `<a href>`, not
  `onClick`. This is a sitewide internal-linking surface; if it is client-only it
  contributes nothing to crawl discovery.
- Data comes from one cached read (`catalog:categories:all`,
  `catalog:subcategories:all` + top brands per subcategory), shared with the
  resolver's cached maps. No per-hover fetch.
- Rendered in the layout, so it appears on every page — meaning every page in the
  app links into the catalog.
- "Popular right now" is the top models by `listing_count` — a rotating set of deep
  links that keeps the deepest tier crawlable from the shallowest surface.
- Keyboard accessible: the trigger is a `<button aria-expanded>`, the panel is
  reachable by Tab, `Esc` closes, focus returns to the trigger.
- Mobile: `MobileMenu.tsx` gets the same tree as an accordion, not a hover panel.

**Search bar**: `SearchBar.tsx` suggestions (backed by
`app/api/search/suggestions/route.ts`) gain a second result group — matched catalog
**nodes** above matched listings:

```
┌────────────────────────────────────────────┐
│ iphone 13                                  │
├────────────────────────────────────────────┤
│ BROWSE                                     │
│ 🗂  iPhone 13          24 listings  €320+   │  → /catalog/…/iphone-13
│ 🗂  iPhone 13 Pro       8 listings  €520+   │
│ 🗂  Used iPhone 13     18 listings         │  → /catalog/…/iphone-13/used
├────────────────────────────────────────────┤
│ LISTINGS                                   │
│ 📱 iPhone 13 128GB, good — €420, Zagreb    │
└────────────────────────────────────────────┘
```

This is the highest-intent path in the product: someone typing a model name wants
the model page, not a filtered result set.

---

## 4. Home page

Three fixes, all small, all high-leverage.

| Component | Change |
|---|---|
| `CategoryCard.tsx:88` | `/marketplace?cat={slug}` → `/{locale}/catalog/{localizedSlug}` |
| `BentoCategoryCard.tsx:90` | same |
| `CategoriesSection.tsx:175`, `CategoriesBento.tsx` | `/marketplace/categories` → `/{locale}/catalog` |
| `BrandCard.tsx:46` | `router.push(...)` → a real `<Link href>` into the brand's `/catalog/` chain. **This is the one that currently makes brand pages invisible to crawlers from the home page.** |

Plus one addition — a **trending catalog rail** below the existing listings
carousel:

```
Popular searches on Swibba
[ Used iPhone 13 ] [ BMW 3 Series ] [ Nike Air Max ] [ Samsung Galaxy S22 ]
[ Phones in Zagreb ] [ Cars for rent in Cairo ] [ Laptops under €500 ]
```

Sourced from the top nodes and modifier permutations by `listing_count` and
`subscriber_count`, filtered to those in `index` state. It gives the home page —
the strongest page on the domain — a set of deep links into the catalog that
changes as inventory changes.

---

## 5. Footer — the cheapest win available

`useFooterConfig.ts` currently has no category links. It gets two new columns,
rendered on every page in the app:

```
Browse                      Popular cities
Electronics                 Phones in Zagreb
Automotive                  Cars in Cairo
Fashion                     Laptops in Split
Home & Appliances           Furniture in Rijeka
Sports                      Phones in Alexandria
Real Estate                 …
All categories →            All locations →
```

- Top 6–8 categories and top 6–8 city permutations, all `index`-state only.
- Server-rendered `<a href>`.
- This is a sitewide link to the catalog from literally every page, including the
  product pages that accumulate the most external links.

---

## 6. Catalog hub — `/{locale}/catalog`

The page that makes the whole tree navigable in one screen, and the target of
"All categories" links everywhere else.

```
Browse everything on Swibba
6 categories · 118 subcategories · 4,812 models · 3,240 live listings

┌─ Electronics ────────────────────────────────────────────────────┐
│ 342 listings · from €12                                          │
│ Phones · Laptops · Audio · Cameras · Wearables · TVs · Gaming     │
│ Popular: iPhone 13 · Galaxy S22 · MacBook Air M2                  │
└──────────────────────────────────────────────────────────────────┘
┌─ Automotive ─────────────────────────────────────────────────────┐
│ 118 listings · from €900                                         │
│ Cars · Motorcycles · Parts · Accessories                          │
│ Popular: BMW 3 Series · Toyota Corolla · Mercedes C-Class         │
└──────────────────────────────────────────────────────────────────┘

Browse by city
Zagreb (412) · Cairo (388) · Split (204) · Rijeka (166) · …
```

Every subcategory, popular model and city named here is a crawlable link. This is
the page that guarantees no tier-2 or tier-3 node is more than two clicks from the
home page — which is the click-depth target that actually drives indexation.

`app/[locale]/marketplace/categories` 308s here, so existing links land correctly.

---

## 7. Product detail page

The product page is where external links and social shares land, so it is the
strongest authority source pointing *into* the catalog.

`app/[locale]/marketplace/[slug]` gains:

1. **A breadcrumb** using the new `src/shared/components/Breadcrumb.tsx`, with the
   full localized chain — every level a link into `/catalog/`:
   ```
   Home / Catalog / Electronics / Phones / Apple / iPhone / iPhone 13 / this listing
   ```
   It already has the chain data: `listings` carries `category_id`,
   `subcategory_id`, `brand_id`, `series_id`, `model_id`.

2. **A "More iPhone 13 on Swibba" block** below the listing:
   ```
   ┌────────────────────────────────────────────────────────────┐
   │ More iPhone 13                                             │
   │ → All 24 iPhone 13 listings          from €320             │
   │ → Used iPhone 13 (18)                                      │
   │ → iPhone 13 in Zagreb (7)                                  │
   │ → iPhone 13 for rent (2)                                   │
   │ → iPhone 13 buying guide & prices                          │
   └────────────────────────────────────────────────────────────┘
   ```
   This also serves the user: someone looking at one iPhone 13 usually wants to
   compare it against the others.

3. **`BreadcrumbList` JSON-LD** extended to the full chain, replacing the current
   `generateBreadcrumbJsonLd` in `meta-tags.service.ts` which uses query-string
   URLs (`?category={id}`, `?subcategory={id}`) — those point at non-canonical,
   non-indexable destinations today.

That third item is a genuine bug fix: the product pages are currently telling
Google their breadcrumb parents are query-string URLs.

---

## 8. Marketplace search page

`app/[locale]/marketplace` stays the faceted search surface. The relationship runs
both ways:

**Search → catalog.** When a user's active filters correspond exactly to a catalog
node or an indexable permutation, offer the landing page:

```
┌──────────────────────────────────────────────────────────────┐
│ Showing 18 results · Phones · Apple · iPhone 13 · Used       │
│ 📖 Read the Used iPhone 13 buying guide & price analysis →   │
└──────────────────────────────────────────────────────────────┘
```

Implemented by reversing the filter state through the resolver. Only shown when the
target is in `index` state, so it never advertises a thin page.

**Catalog → search.** Every "View all N listings" and stat-strip link goes into the
marketplace with `SearchFilters` prefilled — reusing the existing filter shape
rather than adding a parallel one.

**Zero-results state.** The most valuable place to link out, because the user has
stated an intent the inventory cannot satisfy:

```
No listings match "iphone 13 zagreb"

📖 iPhone 13 — prices, specs and what to check    → catalog page
🔔 Get notified when one is listed in Zagreb      → creates a catalog_alert
🗂  Browse all Phones in Zagreb (34)              → modifier page
```

---

## 9. Store and brand pages

| Page | Addition |
|---|---|
| `marketplace/store/[slug]` | "This store sells in: Phones · Laptops · Audio" — links into `/catalog/` for each subcategory the store has inventory in |
| `marketplace/brands` | Each brand card links into its `/catalog/` chain rather than the old `/marketplace/brand/{slug}` |
| `marketplace/brand/[slug]` | 308s into `/catalog/` (see [01 §6](01-url-architecture.md)) |

---

## 10. Dashboard surfaces

Sellers benefit from these pages too, and it drives supply.

| Surface | Addition |
|---|---|
| Listing create/edit, after catalog matching | "See the 24 other iPhone 13 listings and their prices →" — helps the seller price correctly, which improves listing quality |
| `dashboard/listings` per-row | Link to the model page the listing is attached to |
| `dashboard/inventory` | Link from each product to its catalog node |
| Catalog managers | Content-status column links to the live page (see [09 §3](09-admin-dashboard.md)) |

The listing-creation link is the one with real business value: a seller who sees the
live price range before publishing prices realistically, which raises conversion on
the very page that sent them there.

---

## 11. Notifications and email

| Channel | Link |
|---|---|
| Availability alert notification | `action_url` → the **listing** (that is what they asked for), with a secondary link to the catalog node |
| Alert confirmation email | back to `source_path`, the catalog page they subscribed from |
| "No matches yet" digest (optional, later) | the catalog node + related nodes with supply |

---

## 12. Click-depth targets

Click depth from the home page is a direct input to how thoroughly Google crawls a
site. Targets:

| Tier | Max clicks from home | Guaranteed by |
|---|---|---|
| Catalog hub | 1 | header + footer, every page |
| Category | 1 | header mega-menu, home category grid, footer |
| Subcategory | 2 | mega-menu panel, catalog hub, category page child grid |
| Brand | 2 | mega-menu panel, subcategory page child grid |
| Series | 3 | brand page child grid |
| Model | 3 | mega-menu "popular", home trending rail, series child grid |
| Indexable modifier | 4 | model page modifier cluster, footer city links |

Nothing indexable is deeper than four clicks. Verify with a crawl:

```bash
# after phase 5, crawl from the home page and report depth per URL pattern
npx --yes @lhci/cli@0.14.x collect --url="$BASE/en" || true
# or any crawler; the assertion is: no /catalog/ URL in the sitemap has depth > 4
```

---

## 13. Internal-linking rules

Four rules that keep the graph healthy as it grows:

1. **Never link to a non-`index` page from a template.** The modifier cluster, the
   footer city list, the mega-menu and the trending rail all filter on
   `getIndexationState`. A link with a count is a promise; an empty page behind it
   is how a site earns a doorway-page classification.
2. **Always show the count.** `Used iPhone 13 (18)` sets an expectation the page
   meets. It also makes a broken link obvious to a human reviewer.
3. **Real `<a href>`, always.** No `router.push` for navigation between content
   pages. This is the specific defect in `BrandCard.tsx:46` today.
4. **One destination per concept.** After migration there is exactly one URL for
   "the Electronics category". Every surface uses it. No component may construct
   `/marketplace?cat=` again — worth an ESLint `no-restricted-syntax` rule.

---

## 14. Work items

Added to [10-tasks.md](10-tasks.md); collected here for review.

### Phase 1

- [ ] `CategoriesBar.tsx` — read live categories from the cached map, drop the
      hardcoded `categoriesName` array, link to `/catalog/`
- [ ] `CategoryCard.tsx`, `BentoCategoryCard.tsx` — `/marketplace?cat=` → `/catalog/`
- [ ] `CategoriesSection.tsx`, `CategoriesBento.tsx` — hub links → `/{locale}/catalog`
- [ ] `BrandCard.tsx` — `router.push` → `<Link href>` into the `/catalog/` chain
- [ ] `useFooterConfig.ts` — Browse + Popular cities columns
- [ ] `app/[locale]/catalog/page.tsx` — the hub
- [ ] ESLint rule banning `marketplace?cat=` and `marketplace/categories/`

### Phase 2

- [ ] Header mega-menu panel (server-rendered, live data, keyboard accessible)
- [ ] `MobileMenu.tsx` — same tree as an accordion
- [ ] Product detail: breadcrumb + "More {model}" block
- [ ] `meta-tags.service.ts` — `generateBreadcrumbJsonLd` uses `/catalog/` paths,
      not `?category={id}`

### Phase 3

- [ ] `app/api/search/suggestions/route.ts` — a BROWSE group of catalog nodes
- [ ] Home trending catalog rail
- [ ] Marketplace: filters-match-a-node banner
- [ ] Store page: "sells in these categories"

### Phase 4

- [ ] Zero-results state: catalog page + alert + broader modifier page
- [ ] Listing create/edit: price-comparison link to the model page
- [ ] Alert emails and notifications linking back to `source_path`

### Phase 5

- [ ] Crawl-depth audit; assert nothing indexable is deeper than 4 clicks
- [ ] Orphan check: every `index`-state URL has at least one internal link
