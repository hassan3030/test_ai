# 12 — Risks, Trade-offs & Rollback

---

## 1. Risk register

Ordered by expected damage, not by likelihood.

### R1 · Programmatic pages read as doorway / thin content → sitewide demotion

**Severity**: critical — this can suppress the *entire* domain, not just `/catalog/`.

**Why it happens**: thousands of URLs generated from a template, each with a
paragraph of near-identical AI text and a grid of the same listings. Google's
classifier is explicitly tuned for this shape.

**Mitigations**, all of which must hold together:

| Guard | Where |
|---|---|
| Sibling-duplication check (≤ 80% trigram overlap) | quality gate #10 |
| Minimum 250-word body, 3–6 specific FAQs | gate #2, #8 |
| Native per-language generation, not translation | [03 §6](03-content-pipeline.md) |
| Live, node-specific data on every page (prices, cities, condition mix) | context bundle + hero stats |
| Supply thresholds before a modifier page is indexable | [06 §1](06-seo-structured-data.md) |
| Modifier URLs enumerated from real data, never combinatorially | [06 §7](06-seo-structured-data.md) |
| Internal links only to gate-passing permutations, with real counts shown | `CatalogModifierCluster` |

**Early warning**: GSC → Pages, exclusion reasons. A rise in "Crawled – currently
not indexed" across `/catalog/` means Google is judging the pages not worth indexing.
That is the signal to raise thresholds and word-count minimums, not to add more URLs.

**If it happens**: set every modifier permutation to `noindex`, drop the sitemap to
tiers 1–3 only, and raise the body minimum to 400 words. Recovery is measured in
months, which is why the guards are non-negotiable up front.

---

### R1b · Faceted-navigation index explosion

**Severity**: critical — the same failure class as R1, reached by a different route.

**Why it happens**: attribute facets stacked with condition, listing type and city
produce a cross-product. For one model with 3 storage × 5 colours × 8 conditions ×
3 listing types × 50 cities that is 44,063 URLs; across the catalog and 7 locales,
**1.5 billion**. Every one resolvable, almost all empty.

**Mitigations** — all in [15](15-facets-and-variants.md):

| Guard | Detail |
|---|---|
| At most ONE attribute per indexable URL | never `/256gb/gold` |
| At most TWO dimensions, from a declared list | `INDEXABLE_FACET_SHAPES`, one reviewable array |
| Three or more dimensions never indexable | regardless of supply — the shape gate runs before the threshold gate |
| Max two `path` attributes per subcategory | validated in `apply-schema.mjs`; the dashboard rejects a third |
| Numeric attributes must be `banded` | `seo_role: 'path'` on a numeric definition is a validation error |
| `query`-role facets never crawled | `Disallow: /*/catalog/*?` with an `Allow` for `?page=` |
| Facet content composed, not generated per URL | one AI call per node fills `facet_notes` for all its values |

Ceiling falls from 44,063 to ~118 per model, and supply gating takes that to ~10–15.

**Early warning**: GSC → Pages, "Duplicate, Google chose a different canonical"
rising on `/catalog/` paths. That is Google saying these pages are the same page.
Tighten `INDEXABLE_FACET_SHAPES` or raise thresholds — **never add shapes**.

---

### R2 · Localized slugs collide, churn, or 404

**Severity**: high — a 404 on a ranking URL loses the ranking.

**Failure modes**:
- Two subcategories in one category get the same Arabic slug
- An editor renames a slug on a page that already ranks
- Arabic strings that look identical differ by Unicode normalisation form
- A brand slug collides with a condition token (`used`)

**Mitigations**:
- Per-language uniqueness validated in the five catalog write routes; `409` on collision
- `catalog_slug_history` written before every change; resolver 308s from old slugs
- Rows in `catalog_slug_history` are never deleted
- NFC-normalise both sides of every slug comparison
- `RESERVED_CATALOG_SLUGS` rejected at write time
- `check-slug-collisions.mjs` in CI as the backstop
- The catalog manager shows an explicit warning before saving a slug change

**Residual risk**: parent-scoped tiers (subcategory, series, model) rely on app-layer
uniqueness rather than a DB constraint, because a portable composite unique across a
relation is not expressible here. The CI audit is what closes that gap — it must
actually run on every PR.

---

### R3 · Resolver ambiguity between catalog slugs and modifier tokens

**Severity**: high — an ambiguous path either 404s a real page or shadows a modifier.

**Mitigation**: three layers.
1. Catalog match always wins at a given position (a brand named "used" resolves as
   a brand).
2. Catalog slugs cannot equal a reserved token in any locale — rejected at write time.
3. Modifier vocabulary is closed and cached; an unrecognised tail 404s rather than
   guessing.

**Residual risk**: city slugs are deliberately *not* reserved, so a brand and a city
can share a name. That is safe only because a city can appear only after the catalog
chain has stopped resolving. If a future tier is added below `model`, this invariant
must be re-checked.

---

### R4 · AI cost blowout

**Severity**: high — 6,300 nodes × 7 locales ≈ 44,000 model calls for full coverage.

**Mitigations**:
- `source_hash` idempotency with **bucketed** volatile inputs — a price drifting 3%
  must not trigger seven regenerations
- 7-day cooldown unless `force`
- Per-run batch ceiling in `catalog_content_settings.batch_size`
- Backfill prioritised by `listing_count`, so spend tracks revenue potential
- `--dry-run` prints a cost estimate before any spend
- One `writeGenerationLog` row per call → the existing cost dashboard covers it
- `catalog_content_settings.generation_enabled` kill switch, separate from the listing pipeline's

**Early warning**: the Pipeline tab's rolling 30-day cost and cost-per-published-page.

**If it happens**: flip `catalog_content_settings.generation_enabled` off. Pages keep working — they fall
back per [03 §8](03-content-pipeline.md) and simply stay `noindex` until content exists.

---

### R5 · Truncated AI JSON → silent blank drafts

**Severity**: medium, but insidious — it fails quietly.

**Why**: `gpt-5.5` is a reasoning model and reasoning tokens count against
`max_output_tokens`. The listing-enrichment default of `1500` is too small for this
payload; the JSON truncates mid-object and the parse fails, or worse, produces a
partial object that passes shape validation with empty strings.

This has already bitten the listing-enrichment pipeline once.

**Mitigations**:
- This pipeline requests its own ceiling (≥ 6000), never inherits the listing value
- A parse failure is treated as retryable and logs the raw response length — a length
  suspiciously close to the ceiling is the fingerprint
- Gate check #2 (word count) catches a partial body that parsed
- Gate check #11 (placeholder scan) catches empty-ish output

---

### R6 · Client/server boundary regression re-hides content

**Severity**: high — it silently undoes the entire point of the feature.

**Why**: someone adds a `useEffect` fetch to a `/catalog/` component six months from now
because that is the pattern used everywhere else in `app/[locale]/marketplace/`.
The page still *looks* fine in a browser.

**Mitigations**:
- The engineering rule is stated in [10 §Cross-phase](10-tasks.md) and at the top of
  [04](04-rendering-caching.md)
- The `curl | grep -c '<h1>'` + word-count loop in
  [11 §2](11-verification.md) is a cheap CI check — add it to the pipeline, not just
  the runbook
- Fifteen of eighteen new components are server components, so the default a
  developer copies is the correct one

---

### R7 · Sitemap advertises `noindex` URLs

**Severity**: medium — wastes crawl budget and signals low quality.

**Why**: two independent implementations of "should this be indexed" drift apart.

**Mitigation**: there is exactly one `getIndexationState`, and the sitemap shard
builder calls it. The random-sample leak check in [11 §4](11-verification.md) is the
regression test; if it ever prints, something bypassed the shared function.

---

### R8 · ISR staleness shows a wrong price

**Severity**: low-medium — erodes trust more than rankings.

**Mitigation**: 1-hour `revalidate` ceiling, plus a five-tag fan-out on every
`listings` webhook. The page's hero stats and its listing grid come from the *same*
cached read, so a user never sees "24 listings" above a grid of 19 — worst case both
are an hour old, which is consistent if slightly stale.

**Residual risk**: the indexation gate can be up to an hour behind reality, so a page
can briefly be `noindex` after crossing its threshold. Harmless.

---

### R9 · Old `/marketplace/categories/*` URLs lose accumulated authority

**Severity**: medium.

**Mitigations**:
- `permanentRedirect()` (308, which Google treats as 301) rather than deleting
- Old routes kept indefinitely — a cached redirect costs nothing
- New sitemap submitted immediately so Google discovers the targets fast
- GSC monitored for the authority transfer over 4–8 weeks

**Residual risk**: a 4–8 week dip in the redirected URLs' rankings is normal and
should be expected rather than treated as a regression.

---

### R10 · Dev-only Directus changes never reach prod

**Severity**: high — the feature simply does not work on prod, in a way that is not
obvious from the code.

**Why**: Directus schema, public-role permissions and flows are database state. A
code deploy carries none of it. This project has hit this before with the public-role
PII permissions and the store-manager notification flows.

**Mitigations**:
- Every change ships as an idempotent script under `scripts/marketing-content/`
- A snapshot is committed under `docs/content-as-marketing/directus-snapshot/`
- [11 §14](11-verification.md) is a prod checklist, rehearsed on a clone first
- The specific traps called out explicitly: public-role permissions,
  `REVALIDATE_SECRET` matching between app env and *both* flow headers, and
  `catalog_content_settings.system_prompt` being seeded

---

### R11 · Notification spam from the alerts flow

**Severity**: medium — mass unsubscribes and domain reputation damage.

**Failure modes**: every edit to a live listing re-notifies; a popular model notifies
thousands at once; a seller is notified about their own listing; someone matching via
three alerts gets three messages.

**Mitigations**: all four are addressed in [07 §3](07-availability-alerts.md) —
status-transition guard in the flow *and* re-checked in the route, 24-hour throttle
per alert, 10-notification lifetime cap, 200-recipient batch cap with the remainder
queued, recipient de-duplication, and explicit self-exclusion on `user_id`.

---

### R12 · `catalog_alerts` email leak

**Severity**: high — PII, and the go-live audit already found live public-role leaks
on `store_addresses` and `stores`.

**Mitigations**: no public-role permission at all on the collection; email never in
any response body including the operator report; never logged; guest rows created
only by the route with the admin token after rate limiting; the demand report
aggregates counts only.

---

### R13 · Polymorphic `entity_id` has no referential integrity

**Severity**: low.

**Consequence**: deleting a model leaves an orphan `catalog_content` row.

**Mitigations**: `sweep-orphans.mjs` weekly (archives, never deletes, so content
survives an accidental entity deletion); the `entity_label` denormalised field makes
orphans visible in the Directus list view; the unique constraint prevents duplicates.

This is the accepted cost of the polymorphic design — see the trade-off table below.

---

### R14 · Build time grows with `generateStaticParams`

**Severity**: low.

**Mitigation**: `generateStaticParams` is scoped to ~500 paths × 7 locales, and
`dynamicParams = true` means anything omitted renders on demand. If the build gets
slow, drop `getTopNodesByDemand` and pre-render only categories and subcategories.
Nothing about correctness depends on pre-rendering.

---

### R15 · Content contradicts reality

**Severity**: medium — an AI page confidently quoting a €300–500 range for something
now selling at €900 is worse than no page.

**Mitigations**: gate check #16 validates any price-shaped number in
`price_guidance` against the live range; the refresh cron regenerates when
`price_median` moves > 25% or `listing_count` moves > 50%; the *live* price block is
always rendered from current aggregates, separately from the editorial prose, so the
authoritative number on the page is never the AI's.

---

## 2. Trade-offs taken deliberately

| Decision | Chosen | Rejected | Why | What it costs |
|---|---|---|---|---|
| Content storage | polymorphic `catalog_content` | extend five `*_translations` | one pipeline / flow / gate / admin UI; existing collections untouched | no FK on `entity_id`; a raw-UUID field in Directus needing the `entity_label` workaround; one extra query per page |
| URL scheme | `/catalog/` prefix | root-level or under `/marketplace/` | no collision with product, store, or top-level app routes; path depth identifies the tier | two extra characters in every URL |
| Slugs | localized per language | one stable English slug | an Arabic query in Egypt lands on an Arabic URL — the whole point | slug uniqueness, history and redirect machinery |
| Publishing | auto-publish on gate pass | human review gate | scales to thousands of nodes without a content team | a gate false-negative delays a good page; a false-positive publishes a mediocre one |
| Zero-supply pages | render + `noindex` + subscribe | 404, or index anyway | users get value, Google gets only what is worth indexing, demand is captured | crawl budget spent on pages that will not be indexed |
| Language generation | native per language | translate from English | local search phrasing is what ranks locally | 7× the model calls |
| Listings grid | client component, props-fed | fully server-rendered | interactivity without hiding content | the RSC boundary rule must be maintained by convention |
| Matching logic | in the route handler | in Directus flow operations | multi-condition matching with alias expansion is unmaintainable as a flow chain | one more app endpoint to secure |
| Modifier order | fixed canonical order, redirect otherwise | accept any order | one canonical URL per permutation | a redirect hop on non-canonical entry |
| Pagination | `?page=N`, `noindex` for N ≥ 2 | path-based `/page/2`, indexed | avoids competing with the tier page for the same query | deep listings rely on the grid's links for discovery |
| Attribute facets | path segment for ≤ 2 demand-proven attributes per subcategory; query param for the rest | all facets in the path, or all in query params | captures "iphone 13 256gb" without opening a 1.5-billion-URL space | a genuinely high-demand third attribute needs a deliberate policy change, not a config toggle |
| Variants | facet views on the model page now, with the URL designed so a future `model_variants` entity inherits the same address | build the variants system first | ships ranking value now; the later migration is data-only, no redirect map across ranking URLs | `is_variant` currently has no table behind it, so the facet page is the variant page for the time being |

---

## 3. Rollback

Each phase can be reverted independently. Nothing in phases 1–6 destroys existing data.

| Phase | Rollback | Data loss |
|---|---|---|
| 0 | Leave the collections in place — they are additive and unread by anything else. Or drop them via `apply-schema.mjs --revert`. | none |
| 1–2 | Remove `app/[locale]/catalog/`. Revert the three redirect files to their previous bodies (they are in git). `/marketplace/categories/*` and `/marketplace/brand/*` work again immediately. | none |
| 3 | Set `ai_settings.ai_generation_enabled = false` and disable the generate flow. Existing content stays and keeps rendering. | none |
| 4 | Disable the alert flow; hide the notify-me card behind a feature flag. Subscriptions are retained, just not matched. | none — but subscribers stop being served, which is a promise broken; notify them if the outage is longer than a day |
| 5 | Revert `app/sitemap.ts` to the single-file version in git. Re-submit in GSC. | none |
| 6 | Cosmetic; revert individual commits. | none |

### Emergency SEO brake

If GSC shows a quality problem and the cause is not yet identified, one change makes
every `/catalog/` page invisible to search while staying fully usable:

```ts
// src/features/catalog-content/lib/indexation.ts
const GLOBAL_NOINDEX = process.env.CATALOG_GLOBAL_NOINDEX === '1';
```

With that env var set, `getIndexationState` returns `noindex` for everything and the
sitemap shards empty out — because both read the same function. Pages still render,
users still get content, subscriptions still work. That is the value of having one
source of truth for indexation: the brake is a single flag rather than an audit.

### The one thing that is hard to undo

Slug changes. Once Google has indexed `/ar/catalog/الكترونيات/هواتف`, reverting to
English slugs means another migration and another authority transfer. Get the
localized slugs right in phase 1 — review the backfill output before publishing,
rather than after.
