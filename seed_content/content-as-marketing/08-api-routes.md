# 08 — API Routes

Every route handler this feature adds or changes, with its auth model and contract.

## 1. Auth models in use

| Model | How | Used by |
|---|---|---|
| **Webhook** | `Authorization: Bearer ${REVALIDATE_SECRET \|\| DIRECTUS_ADMIN_TOKEN}` | generate, alerts/match, revalidate — the same scheme `app/api/seo-worker/route.ts` already uses |
| **Session** | Directus session cookie → resolved user | alerts create/list/delete |
| **Manager** | Session + role check, mirroring `src/lib/ai/managerGuard.ts` | manual regeneration, review-queue mutations |
| **Token** | Opaque `catalog_alerts.token` in the URL | guest confirm / unsubscribe |
| **Cron** | `Bearer ${CRON_SECRET \|\| REVALIDATE_SECRET}` | refresh cron, same as `app/api/cron/auto-complete` |

> The dashboard/admin routes in this codebase call Directus with the **admin
> token**, which bypasses Directus policies. So every authorisation rule must be
> enforced in the route handler too. Never rely on the Directus policy alone.

---

## 2. New routes

### `POST /api/catalog-content/generate`

Generate or regenerate editorial content for one catalog node.

**Auth**: webhook, or manager session.

```jsonc
// request
{
  "entity_type": "model",              // required
  "entity_id": "9f3c…",                // required
  "locales": ["en-US", "ar-SA"],       // optional; default: all published languages
  "market": "EG",                      // optional; null = global content
  "force": false,                       // optional; bypass source_hash + cooldown
  "reason": "flow:update"              // optional; recorded in the log
}
```

```jsonc
// 202 Accepted — work continues after the response
{
  "accepted": true,
  "entity_type": "model",
  "entity_id": "9f3c…",
  "locales": 7
}

// 200 OK — nothing to do
{ "skipped": true, "reason": "unchanged" }   // unchanged | cooldown | ai_disabled

// 200 OK — synchronous manager-triggered run
{
  "content_id": "…",
  "content_version": 3,
  "quality_score": 0.94,
  "results": {
    "en-US": { "status": "published", "word_count": 412, "passed": true },
    "hi-IN": { "status": "draft", "passed": false,
               "failed_checks": ["language_match"] }
  },
  "usage": { "input_tokens": 18420, "output_tokens": 9310, "cost_usd": 0.11 }
}
```

Behaviour:

- Returns `202` **immediately** for webhook calls and does the work after
  responding, so a Directus flow retry storm cannot pile up requests.
- Returns `200` synchronously for manager calls so the dashboard can show results.
- Idempotent on `source_hash` unless `force`.
- Writes exactly one `writeGenerationLog` row per model call.
- Calls `POST /api/revalidate` on success.
- Errors: `401` bad auth · `400` unknown `entity_type` or missing id ·
  `404` entity not found or not published · `409` a generation for this entity is
  already in flight · `429` rate limited · `502` provider failure after retries ·
  `503` `catalog_content_settings.generation_enabled = false` when called by a manager (webhooks get the
  `skipped` shape instead).

Implementation: thin handler over
`src/features/catalog-content/services/generate.service.ts`. See
[03-content-pipeline.md](03-content-pipeline.md).

---

### `POST /api/catalog-content/alerts`

Create an availability subscription.

**Auth**: session, **or** anonymous with `email` (guest path).

```jsonc
// request
{
  "entity_type": "model",
  "entity_id": "9f3c…",
  "condition": "used",              // optional; enum value or the `used` alias
  "listing_type": "sell",           // optional
  "city_id": "b21e…",               // optional; geo_locations.id
  "max_price": 450,                 // optional
  "currency": "EUR",                // required when max_price is set
  "locale": "en",                   // defaults to the request locale
  "email": "a@b.com",               // required only when unauthenticated
  "source_path": "/catalog/electronics/phones/apple/iphone/iphone-13/used/in-zagreb"
}
```

```jsonc
// 201 — signed in
{ "id": "…", "status": "confirmed", "subscriber_count": 15 }

// 202 — guest, confirmation email sent
{ "status": "pending", "message_key": "catalog.alerts.successGuest" }

// 200 — already subscribed to this exact permutation
{ "already": true, "id": "…", "status": "confirmed" }
```

- Validated with `zod` (already a dependency).
- Rate limits per [07 §2](07-availability-alerts.md).
- **Never echoes `email` back** in any response.
- Increments `catalog_content.subscriber_count` and revalidates
  `catalog-content:{entity_type}:{entity_id}`.
- Errors: `400` validation · `404` unknown entity or city · `409` — not used, a
  duplicate is a `200` · `429` rate limited.

### `GET /api/catalog-content/alerts`

List the current user's alerts. **Auth**: session, required.

```jsonc
{
  "items": [{
    "id": "…",
    "entity": { "type": "model", "id": "…", "name": "Apple iPhone 13",
                "path": "/catalog/electronics/phones/apple/iphone/iphone-13" },
    "condition": "used", "listing_type": null,
    "city": { "id": "…", "name": "Zagreb" },
    "max_price": 450, "currency": "EUR",
    "status": "confirmed",
    "created_at": "2026-08-01T10:00:00Z",
    "notify_count": 2, "last_notified_at": "2026-08-14T08:11:00Z"
  }],
  "total": 6
}
```

Filtered server-side to `user_id = <session user>`, in the handler as well as the
policy.

### `PATCH /api/catalog-content/alerts/[id]`

Update `condition`, `listing_type`, `city_id`, `max_price`, `currency`, or pause.
**Auth**: session; ownership re-checked in the handler. `403` otherwise.

### `DELETE /api/catalog-content/alerts/[id]`

Delete one alert. **Auth**: session; ownership re-checked. Decrements
`subscriber_count`.

### `GET /api/catalog-content/alerts/confirm?token=…`

Guest double opt-in. Sets `status = confirmed`, `confirmed_at = now()`, then
redirects to the `source_path` with a success flag. Single-use: an already-confirmed
token redirects with an "already confirmed" flag rather than erroring.

### `GET|POST /api/catalog-content/alerts/unsubscribe?token=…`

`GET` renders a confirmation page (so an email-client prefetch cannot unsubscribe
someone). `POST` performs it, setting `status = unsubscribed`. Also handles the
`List-Unsubscribe-Post` one-click header.

### `POST /api/catalog-content/alerts/match`

Match a newly published listing against confirmed alerts and create notifications.

**Auth**: webhook.

```jsonc
// request
{ "listing_id": 48211 }

// 200
{
  "listing_id": 48211,
  "candidates": 23,
  "notified": 19,
  "skipped": { "throttled": 3, "own_listing": 1 },
  "queued": 0
}
```

Full matching semantics in [07 §3](07-availability-alerts.md). Notable behaviours:

- Re-verifies `status = 'published'` itself; never trusts the flow's filter alone.
- Caps at 200 recipients per call; the remainder is left for the cron tick and
  reported in `queued`.
- Recipient de-duplication before send when one person matches via several alerts.
- Excludes the listing's own `user_id`.

---

### `POST /api/cron/catalog-content-refresh`

**Auth**: cron.

Two jobs, in this order:

1. **Aggregate refresh** (no AI, always runs): recompute `listing_count`,
   `price_min/median/max`, `price_currency`, `subscriber_count`, `last_counted_at`
   for every `catalog_content` row and `listing_count` for every `geo_locations`
   row. Bust the matching `catalog-aggregates:*` tags.
2. **Content refresh** (AI, bounded): pick up to
   `catalog_content_settings.batch_size` rows matching the staleness rules in
   [03 §2.3](03-content-pipeline.md) and call the generator for each.

Also sweeps: unconfirmed guest alerts older than 7 days, unsubscribed alerts older
than 30 days, and `catalog_content` rows whose entity no longer exists (archived,
not deleted).

```jsonc
{
  "aggregates_refreshed": 6134,
  "cities_refreshed": 212,
  "content_regenerated": 25,
  "swept": { "unconfirmed_alerts": 4, "stale_unsubscribes": 11, "orphans": 0 }
}
```

Returns `200` even on partial failure, with a `errors[]` array — a cron that 500s
gets retried and re-does the expensive half.

---

## 3. Modified routes

### `app/api/revalidate/route.ts`

Currently handles `global_seo` and `listings | listings_translations`, and falls
back to `revalidatePath('/', 'layout')` — which purges the whole app's layout cache
for any unrecognised collection.

Changes:

1. Add the catalog collection → tier map and tag fan-out.
2. Add `catalog_content`, `catalog_content_translations`, `geo_locations`,
   `geo_locations_translations`, `catalog_alerts`.
3. On `listings`, fetch the row's chain columns and bust all five node tags plus
   the city tag, in addition to the existing product-page revalidation.
4. Keep the existing fallback, but log unrecognised collections so the map can be
   completed rather than silently over-purging.

Full mapping in [04 §5](04-rendering-caching.md).

### `app/api/dashboard/catalog/{categories,subcategories,brands,series,models}/[id]/route.ts`

The five catalog write routes need three additions on PATCH/POST:

1. **Accept localized slugs** in the translations payload.
2. **Validate** each slug: non-empty after slugify, not in
   `RESERVED_CATALOG_SLUGS`, unique within `(parent scope, languages_code)`.
   Return `409` with `{ field, languages_code, conflicting_id }` on collision.
3. **Write `catalog_slug_history`** before applying any slug change — base or
   localized. This is what keeps old inbound links alive.

### `app/sitemap.ts`

Rewritten as a sharded sitemap index with `generateSitemaps()`, `alternates` on
every entry, and the shared `getIndexationState` filter. Keeps the `{slug}-{id}`
form for listings. See [06 §5](06-seo-structured-data.md).

### `app/robots.ts`

Adds `Disallow` entries for `/catalog/` client-filter query params only. Does **not**
block `?page=`. See [06 §5](06-seo-structured-data.md).

### `app/llms.txt/route.ts`

Adds a `## Catalog` section built from the index-state catalog tree with each
node's `tl_dr`, above the existing `## Top Listings`. Same content type and cache
headers. See [06 §6](06-seo-structured-data.md).

### `app/[locale]/marketplace/categories/page.tsx`, `categories/[subcat]/*`, `brand/[slug]/*`

Become permanent redirects into `/catalog/`, and the contradictory canonical in
`categories/[subcat]/metadata.ts` goes away with the page body it belonged to.
See [01 §6](01-url-architecture.md).

---

## 4. Routes deliberately **not** added

| Not adding | Why |
|---|---|
| A public catalog-content read API | `/catalog/` pages are server-rendered with the admin client. A public endpoint would be a second code path to keep in sync and a second surface to secure. |
| A listings API for `/catalog/` pages | `app/api/marketplace/business-products` and `model-listings` already cover this. The client grid calls the existing endpoints. |
| A separate breadcrumb/chain API | The chain is resolved server-side and passed as props. |
| A geo/cities API | Cities come from the server-rendered modifier cluster. The notify-me form receives its city list as props. |

Every one of these would be a client-fetch path, which is exactly the pattern this
feature exists to remove.

---

## 5. Error-handling conventions

Match what the codebase already does:

- `NextResponse.json({ message }, { status })` for client-facing errors.
- `console.error('[Catalog Content] …')` with a bracketed prefix, as
  `app/api/seo-worker/route.ts` and `app/api/revalidate/route.ts` do.
- Never leak Directus error bodies to the client; log them, return a generic message.
- Never log `catalog_alerts.email` — log the alert `id`.
- Webhook routes return `200` with `{ skipped, reason }` for expected no-ops, so
  Directus does not retry them as failures. Reserve non-2xx for genuine faults.
- Provider calls get one retry with jittered backoff; a second failure returns
  `502` and is logged with the response length (a truncation symptom).

---

## 6. Route inventory

```
NEW
  app/api/catalog-content/generate/route.ts                  POST
  app/api/catalog-content/alerts/route.ts                    POST, GET
  app/api/catalog-content/alerts/[id]/route.ts               PATCH, DELETE
  app/api/catalog-content/alerts/confirm/route.ts            GET
  app/api/catalog-content/alerts/unsubscribe/route.ts        GET, POST
  app/api/catalog-content/alerts/match/route.ts              POST
  app/api/cron/catalog-content-refresh/route.ts              POST

MODIFIED
  app/api/revalidate/route.ts
  app/api/dashboard/catalog/categories/[id]/route.ts
  app/api/dashboard/catalog/subcategories/[id]/route.ts
  app/api/dashboard/catalog/brands/[id]/route.ts
  app/api/dashboard/catalog/series/[id]/route.ts
  app/api/dashboard/catalog/models/[id]/route.ts
  app/sitemap.ts
  app/robots.ts
  app/llms.txt/route.ts
```
