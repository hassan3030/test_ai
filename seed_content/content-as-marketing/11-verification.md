# 11 — Verification

Every check here is runnable. The ones that matter most are the `curl` checks in
§2 — they are the only way to prove the thing this feature exists to fix.

Assume `BASE=http://localhost:3000` locally, or the dev deployment URL.

---

## 1. Build and types

```bash
npm run type-check
npm run build
```

The likely failure mode of this feature is a React Server Component boundary
error — importing a client-only hook into a server component, or a server-only
module (`import 'server-only'`) into a client component. `npm run build` catches
both; `type-check` alone does not.

Watch the build output for:

- `Error: useState only works in Client Components` → a hook leaked into a server
  component
- `You're importing a component that needs "server-only"` → a service leaked into
  a client component
- The pre-rendered page count. It should be roughly
  `generateStaticParams().length × 7`. A number in the tens of thousands means
  `generateStaticParams` is not scoped and the build will get slow.

---

## 2. Prove server-rendering — the critical check

Today's category page renders its body client-side. This is the check that proves
`/catalog/` does not.

```bash
# 1. The heading is in the HTML
curl -s "$BASE/en/catalog/electronics" | grep -c '<h1'
# expect: 1  (exactly one h1)

# 2. The editorial body is in the HTML, not fetched later
curl -s "$BASE/en/catalog/electronics" | grep -o '<h2[^>]*>[^<]*</h2>' | head
# expect: the h2 headings from catalog_content_translations.body

# 3. Real listing data is in the HTML
curl -s "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13" \
  | grep -oE '(€|\$|EGP|HRK)[0-9,.]+' | head
# expect: prices — NOT an empty result

# 4. No loading spinner as the primary content
curl -s "$BASE/en/catalog/electronics" | grep -ci 'animate-spin'
# expect: 0
```

Run 1–4 against **every tier**:

```bash
for p in \
  "electronics" \
  "electronics/phones" \
  "electronics/phones/apple" \
  "electronics/phones/apple/iphone" \
  "electronics/phones/apple/iphone/iphone-13" \
  "electronics/phones/apple/iphone/iphone-13/used" \
  "electronics/phones/apple/iphone/iphone-13/used/in-zagreb" ; do
  n=$(curl -s "$BASE/en/catalog/$p" | grep -c '<h1')
  w=$(curl -s "$BASE/en/catalog/$p" | sed 's/<[^>]*>/ /g' | wc -w)
  printf '%-60s h1=%s words=%s\n' "$p" "$n" "$w"
done
# expect: h1=1 on every row, words in the high hundreds — not double digits
```

A tier returning `h1=1 words=40` is a page whose shell rendered and whose content
did not.

---

## 3. Localization and hreflang

```bash
# Arabic page returns Arabic content
curl -s "$BASE/ar/catalog/الكترونيات/هواتف" | grep -o '<h1[^>]*>[^<]*</h1>'
# expect: Arabic text in the h1

# dir=rtl is set
curl -s "$BASE/ar/catalog/الكترونيات/هواتف" | grep -o 'dir="rtl"' | head -1

# English slug under /ar/ permanently redirects to the Arabic slug
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  "$BASE/ar/catalog/electronics/phones"
# expect: 308 …/ar/catalog/الكترونيات/هواتف

# hreflang: 7 alternates + x-default, all absolute
curl -s "$BASE/en/catalog/electronics/phones" \
  | grep -o '<link rel="alternate"[^>]*>' 
# expect 8 lines: en-US ar-SA fr-FR es-ES it-IT hi-IN ru-RU x-default

# Reciprocity: the Arabic page lists the same set
curl -s "$BASE/ar/catalog/الكترونيات/هواتف" \
  | grep -c '<link rel="alternate"'
# expect: same count as the English page
```

Canonical consistency — the bug that exists today must not exist here:

```bash
for l in en ar fr es it hi ru; do
  curl -s "$BASE/$l/catalog/electronics" | grep -o '<link rel="canonical"[^>]*>'
done
# expect: each points at ITS OWN locale's URL, all same host+scheme,
#         and never at /marketplace?cat=…
```

---

## 4. Indexation gate

```bash
# A gate-passing tier page is indexable
curl -s "$BASE/en/catalog/electronics/phones" | grep -o '<meta name="robots"[^>]*>'
# expect: index, follow  (or no robots meta at all, which means index)

# A zero-supply modifier page: 200, content, noindex, canonical to ancestor
URL="$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13/for-swap/in-osijek"
curl -s -o /dev/null -w 'status=%{http_code}\n' "$URL"           # expect 200
curl -s "$URL" | grep -o '<meta name="robots"[^>]*>'             # expect noindex, follow
curl -s "$URL" | grep -o '<link rel="canonical"[^>]*>'           # expect the ancestor URL
curl -s "$URL" | grep -ci 'notify'                               # expect >0 — the subscribe card
curl -s "$URL" | sed 's/<[^>]*>/ /g' | wc -w                     # expect high hundreds
```

Then flip it:

```sql
-- publish 5 listings matching model=iPhone 13, listing_type=swap, city=Osijek
```
```bash
curl -X POST "$BASE/api/revalidate" \
  -H "Authorization: Bearer $REVALIDATE_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{"collection":"listings","keys":[<new ids>]}'

curl -s "$URL" | grep -o '<meta name="robots"[^>]*>'
# expect: index, follow   (5 ≥ SUPPLY_THRESHOLDS.listingTypeAndCity)
```

Pagination and filters:

```bash
curl -s "$BASE/en/catalog/electronics/phones?page=2" | grep -o '<meta name="robots"[^>]*>'
# expect: noindex, follow

curl -s "$BASE/en/catalog/electronics/phones?condition=good" | grep -o '<link rel="canonical"[^>]*>'
# expect: the BARE path, no query string
```

Sanity check that nothing bypassed the gate:

```bash
# every sitemap URL must be indexable
curl -s "$BASE/sitemap.xml" | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' \
  | shuf -n 40 | while read -r u; do
      r=$(curl -s "$u" | grep -o 'name="robots"[^>]*noindex' | head -1)
      [ -n "$r" ] && echo "LEAK: $u"
    done
# expect: no output
```

That last loop is the single most valuable regression test in the feature. If it
ever prints, the shared `getIndexationState` has been bypassed somewhere.

---

## 5. Structured data

```bash
# Extract and pretty-print the JSON-LD graph
curl -s "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13" \
  | grep -o '<script type="application/ld+json">.*</script>' \
  | sed 's/<[^>]*>//g' | python3 -m json.tool | head -60
```

```bash
node scripts/marketing-content/13-validate-jsonld.mjs --base="$BASE" --locale=en
```

The script asserts, per tier:

| Tier | Required `@type`s | Forbidden |
|---|---|---|
| category / subcategory / series | `CollectionPage`, `BreadcrumbList`, `ItemList` | `Product`, `AggregateRating`, `LocalBusiness` |
| brand | + `Brand` | same |
| model with offers | `Product`, `AggregateOffer`, `BreadcrumbList` | `AggregateRating`, `LocalBusiness` |
| model without offers | `CollectionPage`, `BreadcrumbList` | `Product`, `AggregateOffer` |
| modifier | `CollectionPage`, `BreadcrumbList` | `LocalBusiness`, `Place` |
| any with ≥3 FAQs | + `FAQPage` | — |

And cross-checks that every marked-up value is visible on the page:

```
AggregateOffer.lowPrice   appears in the rendered text
AggregateOffer.offerCount appears in the rendered text
each FAQPage question     appears in a <summary>
each BreadcrumbList item  appears in the breadcrumb nav
```

Then confirm on a deployed URL with Google's Rich Results Test
(`https://search.google.com/test/rich-results`) for one page per tier. Local
validation catches shape errors; only Google's tool confirms eligibility.

---

## 6. Sitemaps and robots

```bash
# Index lists all shards
curl -s "$BASE/sitemap.xml" | grep -c '<sitemap>'

# Every shard is reachable and well-formed
curl -s "$BASE/sitemap.xml" | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' \
  | while read -r s; do
      printf '%-70s %s\n' "$s" "$(curl -s -o /dev/null -w '%{http_code}' "$s")"
    done
# expect: 200 on every line

# Every entry has hreflang alternates
curl -s "$BASE/sitemap/catalog-models-0.xml" | grep -c 'xhtml:link'
# expect: ≈ 7 × the <url> count

# No shard exceeds the limits
curl -s "$BASE/sitemap/listings-0.xml" | grep -c '<url>'    # expect ≤ 50000
curl -s "$BASE/sitemap/listings-0.xml" | wc -c              # expect < 50MB

# Listing URLs keep the required -{id} suffix
curl -s "$BASE/sitemap/listings-0.xml" | grep -o '<loc>[^<]*</loc>' \
  | sed 's/<[^>]*>//g' | head -3 | while read -r u; do
      printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$u")" "$u"
    done
# expect: 200 (a bare slug 404s — this is why the suffix exists)

# robots
curl -s "$BASE/robots.txt"
# expect: /catalog/ NOT disallowed; ?condition= etc disallowed; ?page= NOT disallowed;
#         sitemap + llms.txt lines present

# llms.txt carries the catalog tree
curl -s "$BASE/llms.txt" | head -40
# expect: "## Catalog" with nested tiers and tl_dr lines
```

---

## 7. Performance

Via the chrome-devtools MCP, desktop preset, one URL per tier:

```
lighthouse_audit  $BASE/en/catalog/electronics
lighthouse_audit  $BASE/en/catalog/electronics/phones
lighthouse_audit  $BASE/en/catalog/electronics/phones/apple
lighthouse_audit  $BASE/en/catalog/electronics/phones/apple/iphone
lighthouse_audit  $BASE/en/catalog/electronics/phones/apple/iphone/iphone-13
```

| Metric | Target |
|---|---|
| LCP | < 2.5 s |
| CLS | < 0.1 |
| TBT | < 200 ms |
| Performance score | ≥ 90 desktop |
| Accessibility score | ≥ 95 |
| SEO score | 100 |

Server-side timings on a cache miss:

```bash
for i in 1 2 3; do
  curl -s -o /dev/null -w 'ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
    "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13?cb=$RANDOM"
done
# expect: ttfb < 0.4s on a miss, < 0.05s on a hit
```

Also confirm the Directus read count per cold render — add a temporary counter to
`catalog-page.service.ts` in dev, or watch the Directus request log. Target ≤ 6.

---

## 8. Caching and revalidation

```bash
# 1. Load a model page, note the price range
curl -s "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13" \
  | grep -oE '(€|\$)[0-9,]+' | head -2

# 2. Change a listing's price in Directus (or publish a new one)

# 3. Fire the webhook the way Directus does
curl -X POST "$BASE/api/revalidate" \
  -H "Authorization: Bearer $REVALIDATE_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{"collection":"listings","keys":[48211]}'

# 4. Reload — the range must reflect the change immediately
curl -s "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13" \
  | grep -oE '(€|\$)[0-9,]+' | head -2
```

Repeat for each mapped collection, asserting the *right* thing is purged and the
whole app layout is not:

| Webhook `collection` | Should change | Should NOT change |
|---|---|---|
| `models_translations` | that model page's name/slug | sibling model pages |
| `catalog_content_translations` | that node's body | its aggregates |
| `listings` | aggregates on all five chain nodes + the city | editorial content |
| `geo_locations` | modifier vocabulary, city pages | tier pages |
| an unmapped collection | logs a warning | (still falls back, but is now visible) |

Bad auth must be rejected:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/revalidate" \
  -H 'Authorization: Bearer wrong' -d '{"collection":"listings"}'
# expect: 401
```

---

## 9. AI pipeline

```bash
# Dry run first — no spend, prints the context bundle and the plan
node scripts/marketing-content/12-backfill-content.mjs --tier=model --limit=3 --dry-run
```

Inspect in the output:

- the context bundle contains real `market` numbers (count, price range, cities)
  and not zeros
- `chain` and `siblings` are populated and **localized**
- `knownSpecs` is present for a model that has `models_attribute_values`
- the estimated cost is plausible

Then a live run:

```bash
node scripts/marketing-content/12-backfill-content.mjs --tier=model --limit=3
```

Verify:

```bash
# Content landed in all 7 languages
curl -s "$DIRECTUS/items/catalog_content?filter[entity_id][_eq]=$MODEL_ID\
&fields=status,quality_score,translations.languages_code,translations.status,\
translations.word_count" -H "Authorization: Bearer $DIRECTUS_ADMIN_TOKEN" \
  | python3 -m json.tool
```

- [ ] 7 translation rows, one per language
- [ ] `word_count ≥ 250` on each published row
- [ ] each language is **actually in that language** — read the Arabic and Hindi
      output, do not trust the check alone
- [ ] no meta-commentary ("based on the provided data", "as an AI")
- [ ] `meta_title ≤ 60`, `meta_description ≤ 160`
- [ ] 3–6 FAQs, answers specific to the model
- [ ] prices quoted in `price_guidance` fall inside the live range
- [ ] `slug_suggestion` is sensible and localized
- [ ] a cost row exists in the AI logs for each call

Idempotency and guards:

```bash
# Second run must skip
node scripts/marketing-content/12-backfill-content.mjs --tier=model --limit=3
# expect: skipped: unchanged (or cooldown) for all three

# Force must regenerate and bump content_version
curl -X POST "$BASE/api/catalog-content/generate" \
  -H "Authorization: Bearer $REVALIDATE_SECRET" \
  -d '{"entity_type":"model","entity_id":"'$MODEL_ID'","force":true}'
```

Truncation guard — the known `gpt-5.5` failure mode:

```bash
# Temporarily set catalog_content_settings.max_output_tokens = 800, then generate
# expect: a clean 502 with the response length logged — NOT a silent blank draft
```

Loop guard:

```bash
# Write to catalog_content directly in Directus.
# expect: NO generate webhook fires (catalog_content* is not in the flow's scope)
```

Gate behaviour: pick a node whose sibling already has published content, force a
regeneration, and confirm that near-duplicate output lands as `draft` with
`sibling_dup` in `gate_report` rather than being published.

---

## 10. Availability alerts

```bash
# Subscribe (signed in — pass a session cookie)
curl -s -X POST "$BASE/api/catalog-content/alerts" \
  -H 'Content-Type: application/json' -b "$COOKIE" \
  -d '{"entity_type":"model","entity_id":"'$MODEL_ID'","condition":"used",
       "city_id":"'$ZAGREB_ID'","locale":"en",
       "source_path":"/catalog/electronics/phones/apple/iphone/iphone-13/used/in-zagreb"}'
# expect: 201, status confirmed, subscriber_count incremented
# expect: NO email field anywhere in the response

# Duplicate is a 200, not an error
# (re-run the same command) → { "already": true }
```

Then run the end-to-end script:

```bash
node scripts/marketing-content/14-test-alerts.mjs
```

It must assert:

- [ ] publishing a matching listing creates exactly one `notifications` row per
      subscriber
- [ ] `category = 'alert'`, `collection = 'listings'`, `item = <listing id>`
- [ ] `action_url` includes the `-{id}` suffix and returns `200`
- [ ] `subject`/`message` are in the alert's stored `locale`, not the publisher's
- [ ] a `condition: 'used'` alert matches a `good` listing (alias expansion)
- [ ] a `condition: 'used'` alert does **not** match a `new` listing
- [ ] the listing's own seller is not notified
- [ ] a second publish within 24 h does not re-notify (throttle)
- [ ] editing an already-published listing does not notify (transition guard)
- [ ] one person matching via two alerts receives one notification
- [ ] `max_price` excludes over-budget listings

Guest flow, manually:

- [ ] guest subscribe → `202`, `status = pending`, confirmation email sent
- [ ] confirm link → `status = confirmed`, redirect back to `source_path`
- [ ] a second click on the same link → "already confirmed", not an error
- [ ] `GET` on the unsubscribe URL renders a confirmation page (an email-client
      prefetch must not unsubscribe anyone); `POST` performs it
- [ ] rate limits reject the 6th alert for one email and the 4th per hour per IP

Privacy:

```bash
# Public role must have no access at all
curl -s "$DIRECTUS/items/catalog_alerts" | python3 -m json.tool
# expect: 403

# The demand report must not contain addresses
curl -s "$BASE/api/…/demand" -b "$MANAGER_COOKIE" | grep -c '@'
# expect: 0

grep -rn "alert.email\|\.email" src/features/catalog-content/ | grep -i "log\|console"
# expect: no matches
```

---

## 11. Slugs and redirects

```bash
node scripts/marketing-content/08-check-slug-collisions.mjs
# expect: exit 0, no collisions, no reserved-token slugs, no empty slugs
```

```bash
# Old routes redirect
for u in \
  "/en/marketplace/categories" \
  "/en/marketplace/categories/electronics" \
  "/en/marketplace/brand/apple" ; do
  curl -s -o /dev/null -w "%{http_code} %{redirect_url}  <- $u\n" "$BASE$u"
done
# expect: 308 into /en/catalog/… on each

# Slug history: rename a subcategory's Arabic slug in Directus, then
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  "$BASE/ar/catalog/الكترونيات/<old-slug>"
# expect: 308 to the new slug

# Reserved-token rejection
curl -s -o /dev/null -w '%{http_code}\n' -X PATCH \
  "$BASE/api/dashboard/catalog/brands/$BRAND_ID" -b "$MANAGER_COOKIE" \
  -H 'Content-Type: application/json' -d '{"slug":"used"}'
# expect: 409

# Collision rejection
# PATCH a second subcategory in the same category to an existing sibling slug
# expect: 409 with the conflicting id
```

Modifier ordering:

```bash
# Out of canonical order redirects rather than 404s or duplicates
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13/in-zagreb/used"
# expect: 308 → …/iphone-13/used/in-zagreb

# Nonsense tail 404s
curl -s -o /dev/null -w '%{http_code}\n' \
  "$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13/banana"
# expect: 404
```

---

## 12. Accessibility and RTL

Via the chrome-devtools MCP a11y tooling, on one page per tier:

- [ ] exactly one `<h1>`; no heading level skipped
- [ ] every `<section>` has `aria-labelledby` pointing at a real heading id
- [ ] FAQ works with JS disabled (`<details>`/`<summary>`)
- [ ] full keyboard traversal with a visible focus ring throughout
- [ ] tap targets ≥ 44 px
- [ ] contrast ≥ 4.5:1 in light **and** dark
- [ ] stat-strip numbers have `aria-label` text

RTL, on `/ar/catalog/...`:

- [ ] `dir="rtl"` on the document
- [ ] breadcrumb separators, comparison scroller and stat strip all mirror
- [ ] no `pl-*`/`pr-*`/`text-left`/`text-right` in the new components
      (`grep -rn 'pl-\|pr-\|text-left\|text-right' src/features/catalog-content/components/`
      → expect no matches)
- [ ] prices render LTR inside RTL text
- [ ] no horizontal page scroll at 1280 px or 375 px

---

## 13. i18n completeness

```bash
# All 7 locale files carry the same keys (deep, not just top level)
node -e '
const fs=require("fs");
const flat=(o,p="")=>Object.entries(o).flatMap(([k,v])=>
  v&&typeof v==="object"&&!Array.isArray(v)?flat(v,p+k+"."):[p+k]);
const load=l=>flat(JSON.parse(
  fs.readFileSync("messages/"+l+"/catalogPages.json","utf8")));
const base=load("en");
for (const l of ["ar","fr","es","it","hi","ru"]) {
  const k=load(l);
  const missing=base.filter(b=>!k.includes(b));
  const extra=k.filter(b=>!base.includes(b));
  if (missing.length||extra.length) console.log(l,{missing,extra});
}
'
# expect: no output
```

```bash
# No raw keys leaking into rendered pages
for l in en ar fr es it hi ru; do
  n=$(curl -s "$BASE/$l/catalog/electronics" | grep -oc 'catalogPages\.[a-zA-Z]*\.[a-zA-Z]*')
  echo "$l raw-keys=$n"
done
# expect: 0 on every locale. A non-zero count on dev usually means a stale deploy.
```

```bash
# The new namespace is registered — otherwise every key renders raw
grep -n "catalogPages" src/i18n/config.ts
# expect: hits in BOTH allNamespaces and NAMESPACE_GROUPS
```

---

## 14. Prod parity

Directus schema, public-role permissions and flows live in the Directus database.
They do **not** travel with a code deploy.

Rehearse on a prod clone before prod:

```bash
node scripts/marketing-content/01-apply-schema.mjs        --env=prod-clone
node scripts/marketing-content/01-apply-schema.mjs        --env=prod-clone   # 2nd run: no diff
node scripts/marketing-content/02-apply-permissions.mjs   --env=prod-clone
node scripts/marketing-content/03-seed-geo-locations.mjs  --env=prod-clone
node scripts/marketing-content/06-build-flows.mjs --env=prod-clone
node scripts/marketing-content/06-build-flows.mjs   --env=prod-clone
node scripts/marketing-content/05-backfill-slugs.mjs      --env=prod-clone
```

Then diff against the dev snapshot:

```bash
node scripts/marketing-content/01-apply-schema.mjs --snapshot --env=prod-clone \
  > /tmp/prod-clone-snapshot.json
diff <(python3 -m json.tool docs/content-as-marketing/directus-snapshot/collections.json) \
     <(python3 -m json.tool /tmp/prod-clone-snapshot.json)
```

Prod checklist:

- [ ] all seven scripts replayed, second run is a no-op
- [ ] public-role permissions confirmed **on prod** — verify a public read of
      `catalog_content` returns only `status = published` and only allowlisted fields
- [ ] public read of `catalog_alerts` returns `403`
- [ ] both Directus flows exist and are enabled
- [ ] `REVALIDATE_SECRET` matches between the app env and both flow headers
- [ ] `catalog_content_settings.system_prompt` is seeded (otherwise the prompt is
      inert and every draft will be blank or wrong)
- [ ] sitemap index submitted in Google Search Console
- [ ] privacy-policy CMS content updated for alert emails, in all 7 languages

---

## 15. Attribute facets (see [15](15-facets-and-variants.md))

```bash
M="$BASE/en/catalog/electronics/phones/apple/iphone/iphone-13"

# Single-facet URLs are indexable when above threshold
curl -s "$M/256gb" | grep -o '<meta name="robots"[^>]*>'      # expect: index, follow
curl -s "$M/used"  | grep -o '<meta name="robots"[^>]*>'      # expect: index, follow

# Declared pair: indexable
curl -s "$M/256gb/used" | grep -o '<meta name="robots"[^>]*>' # expect: index, follow

# RULE 1 — two attributes: renders, noindex, canonical to the single-attribute page
curl -s -o /dev/null -w 'status=%{http_code}\n' "$M/256gb/gold"   # expect: 200
curl -s "$M/256gb/gold" | grep -o '<meta name="robots"[^>]*>'      # expect: noindex, follow
curl -s "$M/256gb/gold" | grep -o '<link rel="canonical"[^>]*>'    # expect: …/iphone-13/256gb
curl -s "$M/256gb/gold" | sed 's/<[^>]*>/ /g' | wc -w              # expect: high hundreds

# RULE 3 — three dimensions: never indexable, whatever the supply
curl -s "$M/256gb/used/in-zagreb" | grep -o '<meta name="robots"[^>]*>'
# expect: noindex, follow
curl -s "$M/256gb/used/in-zagreb" | grep -o '<link rel="canonical"[^>]*>'
# expect: …/iphone-13/256gb/used   (nearest indexable ancestor)

# Query-role facets are never indexable
curl -s "$M?ram=4gb" | grep -o '<meta name="robots"[^>]*>'    # expect: noindex, follow
curl -s "$M?ram=4gb" | grep -o '<link rel="canonical"[^>]*>'  # expect: the bare path

# Canonical ordering: wrong order 308s
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$M/used/256gb"
# expect: 308 → …/iphone-13/256gb/used

# Non-canonical value slug 308s
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$M/256-gb"
# expect: 308 → …/iphone-13/256gb

# Unknown option value for this model 404s (not a soft 200)
curl -s -o /dev/null -w '%{http_code}\n' "$M/1tb"            # expect: 404
```

### Normalisation — the check that silently matters most

A facet page must find **all** its inventory, including listings whose raw value
spelling differs:

```bash
# Seed run must cluster spellings, and print them rather than auto-merging
node scripts/marketing-content/04-seed-attribute-option-values.mjs --dry-run \
  | grep -A3 "near-duplicate"
# review: "256GB" / "256 GB" / "256gb" / "256" must land on ONE row

# The facet count matches a direct Directus count over all mapped spellings
curl -s "$M/256gb" | grep -oE '[0-9]+ listings' | head -1
# compare against:
#   /items/listings?aggregate[count]=id
#     &filter[model_id][_eq]=…
#     &filter[listings_attribute_values][value][_in]=256GB,256 GB,256gb,256
# expect: identical. A lower page count means normalisation is dropping inventory.
```

### Policy guardrails

```bash
# Max two `path` attributes per subcategory
node scripts/marketing-content/08-check-slug-collisions.mjs --check-facets
# asserts: ≤2 seo_role='path' per subcategory; no numeric definition marked 'path';
#          no option slug colliding with a condition or listing-type token

# INDEXABLE_FACET_SHAPES contains no shape with two attributes or ≥3 dimensions
node -e '
const {INDEXABLE_FACET_SHAPES:S}=require("./src/features/catalog-content/lib/facet-policy.ts");
for (const s of S) {
  if (s.length > 2) throw new Error("shape too deep: "+s);
  if (s.filter(d=>d==="attribute").length > 1) throw new Error("two attributes: "+s);
}
console.log("ok", S.length, "shapes");
'
```

### Structured data on facet pages

```bash
node scripts/marketing-content/13-validate-jsonld.mjs --base="$BASE" --locale=en --facets
```

Asserts:

- single-attribute facet on an `is_variant` attribute → `Product` +
  `AggregateOffer` with the attribute as `additionalProperty`, **only** when
  `offerCount ≥ 1`
- every other facet shape → `CollectionPage` + `BreadcrumbList` + `ItemList`,
  and **never** `Product`
- the breadcrumb includes the facet as its own level (`… › iPhone 13 › 256GB › Used`)

### robots.txt

```bash
curl -s "$BASE/robots.txt" | grep -A6 'User-Agent: \*'
# expect:  Allow: /*/catalog/*?page=
#          Disallow: /*/catalog/*?
# and NOT a disallow on /*/catalog/ itself, nor on path-based facet URLs
```

### Content cost

```bash
# One AI call per node fills facet_notes for ALL its facet values.
# There must never be one generation call per facet URL.
curl -s "$DIRECTUS/items/catalog_content_translations?filter[catalog_content_id][_eq]=$CID\
&fields=languages_code,facet_notes" -H "Authorization: Bearer $DIRECTUS_ADMIN_TOKEN" \
  | python3 -m json.tool
# expect: one row per language, facet_notes keyed by facet slug, 40–80 words each
```

### Sitemap bound

```bash
# The modifiers shard must stay in the thousands, not the millions
curl -s "$BASE/sitemap/catalog-modifiers-0.xml" | grep -c '<url>'
# expect: < 40000 per shard, and the total shard count small enough to be sane.
# A number in the millions means the facet policy was bypassed.
```

---

## 16. Motion & discovery

### Motion (see [13](13-ui-and-motion.md))

```bash
# Above-the-fold content is at final opacity with JS off:
# load with JS disabled in DevTools, confirm h1 + lede + hero image are visible.

# No layout-shifting properties in any animation
grep -rnE '(transition|@keyframes)[^;]*\b(height|width|top|left|margin|padding)\b' \
  src/features/catalog-content/ app/globals.css
# expect: no matches (animate transform + opacity only)

# No scroll or mousemove listeners added by this feature
grep -rn "addEventListener('scroll'\|addEventListener(\"scroll\"\|'mousemove'" \
  src/features/catalog-content/
# expect: no matches

# Every framer-motion component in this feature honours reduced motion
for f in $(grep -rl "framer-motion" src/features/catalog-content/); do
  grep -q "useReducedMotion" "$f" || echo "MISSING useReducedMotion: $f"
done
# expect: no output
```

Manual, in the browser:

- [ ] `prefers-reduced-motion: reduce` (DevTools → Rendering) → the page is fully
      static and fully usable; nothing is hidden
- [ ] Below-the-fold sections reveal on scroll; a section already in view on load
      does **not** re-animate (`animation-fill-mode: both` + `view()`)
- [ ] Click a child card → its image and title morph into the destination hero and
      `<h1>`; the breadcrumb stays anchored
- [ ] In a browser without View Transitions → instant navigation, no flash
- [ ] CLS measured at 0 on first load with CPU + network throttling on
- [ ] Catalog page JS bundle ≤ the marketplace page (compare `next build` output)

### Discovery (see [14](14-discovery.md))

```bash
# The three broken link patterns are gone
grep -rn "marketplace?cat=" src app
# expect: no matches

grep -rn "categoriesName" src/shared/components/layout/Header/CategoriesBar.tsx
# expect: no matches — the hardcoded array is deleted

grep -n "router.push" src/shared/components/home/BrandsSection/BrandCard.tsx
# expect: no matches — it must be a real <Link href>

# Catalog links are in the server-rendered HTML of pages that are NOT catalog pages
curl -s "$BASE/en" | grep -c 'href="/en/catalog/'
# expect: >10  (home category grid + header mega-menu + footer)

curl -s "$BASE/en/marketplace/some-listing-slug-48211" | grep -c 'href="/en/catalog/'
# expect: >5   (breadcrumb chain + "More {model}" block)

# The footer links from every page
for u in /en /en/about /en/help /en/marketplace; do
  printf '%-20s %s\n' "$u" "$(curl -s "$BASE$u" | grep -c 'href="/en/catalog/')"
done
# expect: non-zero on every row
```

Manual:

- [ ] Header mega-menu opens on hover **and** on keyboard focus; `Esc` closes and
      returns focus to the trigger; every item is a real link
- [ ] Search "iphone 13" → a BROWSE group appears above listing results, linking to
      the model page
- [ ] Marketplace zero-results state offers the catalog page, an alert, and a
      broader modifier page
- [ ] No template links to a non-`index` page: spot-check 10 modifier-cluster and
      footer city links, all return `index, follow`
- [ ] Click depth: every URL in the sitemap is reachable within 4 clicks from `/en`

---

## 17. Regression checks on existing surfaces

This feature touches shared code. Confirm nothing else broke:

- [ ] `/en/marketplace` search still works with all filters
- [ ] a product page `/en/marketplace/{slug}-{id}` still renders, still has its
      `Product` JSON-LD
- [ ] `/en/marketplace/brands` still lists brands
- [ ] `/en/marketplace/store/{slug}` unaffected
- [ ] listing creation and AI enrichment still work — `max_output_tokens` was
      touched, so re-run one AI listing generation end to end
- [ ] the AI settings page still saves, and the prompt fields are still read-only
      outside dev
- [ ] catalog managers can still create/edit all five entity types
- [ ] existing notifications (offers, orders, messages) still deliver — the
      `notifications` collection gained a new producer, not a new shape
- [ ] `/llms.txt` still returns `text/plain` and still lists top listings
- [ ] `/sitemap.xml` still contains every listing URL it contained before
- [ ] the header categories bar still renders on every page, now from live data —
      confirm a newly created Directus category appears without a code change
- [ ] the home page category grid and brand rail still navigate correctly after the
      `router.push` → `<Link>` change
