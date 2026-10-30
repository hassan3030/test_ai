# 07 — Availability Alerts

> *"If no listings, at least we will have content describing the user's needs until
> it's available — and the user can subscribe for updates: when this product is
> available we will notify them."*

This is what turns a zero-supply page from a dead end into a demand-capture asset.
It also produces the single most valuable dataset in the feature: a list of
exactly what buyers want that Swibba does not currently stock.

---

## 1. The loop

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 1. Visitor lands on /en/catalog/…/iphone-13/used/in-zagreb from Google        │
   │    → 0 live listings                                                 │
   │    → page still explains the model, typical prices, what to check    │
   │    → notify-me card is promoted directly under the hero              │
   └───────────────────────────────┬──────────────────────────────────────┘
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 2. They subscribe                                                    │
   │    signed in  → one click, status = confirmed                        │
   │    signed out → email + double opt-in, status = pending              │
   │    → catalog_alerts row, prefilled from the page's modifiers         │
   │    → subscriber_count++ on catalog_content                           │
   └───────────────────────────────┬──────────────────────────────────────┘
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 3. Someone lists a matching iPhone 13 in Zagreb                      │
   │    → Directus flow on listings → status becomes published            │
   │    → match against confirmed catalog_alerts                          │
   └───────────────────────────────┬──────────────────────────────────────┘
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 4. Notification                                                      │
   │    → notifications row (category: alert) in the subscriber's locale   │
   │    → in-app bell + web push + optional email                         │
   │    → action_url deep-links straight to the listing                    │
   │    → last_notified_at / notify_count updated (throttle)               │
   └───────────────────────────────┬──────────────────────────────────────┘
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 5. Feedback into the system                                          │
   │    → subscriber_count feeds the indexation demand override           │
   │    → the demand report tells merchandising what to go source          │
   └──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Subscription

### What gets captured

A subscription is a **node plus optional narrowing**, prefilled from the URL the
visitor is standing on:

| Page | `entity_type` / `entity_id` | `condition` | `listing_type` | `city_id` |
|---|---|---|---|---|
| `/catalog/electronics/phones/apple/iphone/iphone-13` | `model` / iPhone 13 | — | — | — |
| `…/iphone-13/used` | `model` / iPhone 13 | `used` | — | — |
| `…/iphone-13/used/in-zagreb` | `model` / iPhone 13 | `used` | — | Zagreb |
| `…/iphone-13/for-rent/in-cairo` | `model` / iPhone 13 | — | `rent` | Cairo |
| `/catalog/electronics/phones/apple` | `brand` / Apple | — | — | — |

The visitor can loosen or tighten it in the form (condition dropdown, max price),
but the defaults come from the page — so the common case is a single click.

`max_price` + `currency` are optional. `locale` is taken from the request so the
notification arrives in the language they were browsing in.

### Signed in vs guest

| | Signed in | Guest |
|---|---|---|
| Identity | `user_id` | `email` |
| Initial status | `confirmed` | `pending` |
| Confirmation | none needed | double opt-in email with a `token` link |
| Delivery | in-app + push + email | email only |
| Management | `/{locale}/dashboard/favorites` → Alerts tab | `token` link in every email |

Double opt-in for guests is not optional: without it the endpoint is a spam relay
that will burn the sending domain's reputation.

### Deduplication

Two partial unique constraints (see [02 §7](02-data-model.md)) make a duplicate
subscription impossible at the database level. The API responds `200` with
`{ already: true }` rather than `409`, and the UI says "You're already on this
list" — a duplicate click is a normal thing for a person to do, not an error.

### Rate limiting

| Actor | Limit |
|---|---|
| Signed-in user | 50 active alerts total, 10 new per hour |
| Guest email | 5 alerts per email, 3 per hour per IP |
| Unconfirmed guest rows | expire after 7 days, swept by cron |

---

## 3. Matching

### The flow

Built by `scripts/marketing-content/06-build-flows.mjs`, modelled on
`scripts/notifications/build-store-team-notification-flows.mjs` — additive flows
only, re-runnable, and safe to run against prod.

```
name:    Marketing Content / Alert Match
trigger: items.create, items.update on `listings`
filter:  status == 'published'
         AND (on update) the previous status was not 'published'
action:  POST {APP_URL}/api/catalog-content/alerts/match
         Authorization: Bearer {REVALIDATE_SECRET}
         body: { listing_id }
```

The transition guard matters: without it, every subsequent edit to an already-live
listing re-notifies everyone. Directus exposes the previous values on
`items.update`, so the filter compares against them; the route re-checks
`last_notified_at` as a second line of defence.

The heavy lifting lives in the **route**, not in Directus flow operations. Matching
needs a multi-condition query with alias expansion and price comparison, which is
awkward and unmaintainable as a chain of flow operations, and trivial in TypeScript.

### The match query

`app/api/catalog-content/alerts/match/route.ts`

```
Given a listing L:

  chain = [
    ('category',    L.category_id),
    ('subcategory', L.subcategory_id),
    ('brand',       L.brand_id),
    ('series',      L.series_id),
    ('model',       L.model_id),
  ].filter(([, id]) => id != null)

  cityId = lookupGeoLocation(L.location_country, L.location_city)   // may be null

  candidates = catalog_alerts WHERE
      status = 'confirmed'
      AND (entity_type, entity_id) IN chain
      AND (condition     IS NULL OR condition     matches L.condition)
      AND (listing_type  IS NULL OR listing_type  = L.listing_type)
      AND (city_id       IS NULL OR city_id       = cityId)
      AND (max_price     IS NULL OR L.price <= max_price in same currency)
      AND (last_notified_at IS NULL OR last_notified_at < now() - 24h)
      AND user_id <> L.user_id            -- never notify the seller about their own listing
```

**Condition alias expansion.** `condition = 'used'` must match a listing whose
condition is any of `like_new, excellent, good, fair`. The same
`CONDITION_ALIASES` map used by the resolver is used here — one definition, two
consumers.

**Currency.** `max_price` is stored with its `currency`. Compare only when the
currencies match, or convert using the same rate source the listing pipeline
already uses. When conversion is unavailable, treat the price filter as unmet
rather than notifying with a possibly-wrong comparison.

**Broadest-match wins.** A person subscribed to both `model:iPhone 13` and
`model:iPhone 13 + used + Zagreb` gets **one** notification for a listing matching
both — the most specific matching alert is the one recorded as notified, and the
recipient is de-duplicated before sending.

### Notification payload

Written into the existing custom `notifications` collection — no new notification
infrastructure:

```json
{
  "recipient_id": "<uuid>",
  "sender_id": null,
  "category": "alert",
  "status": "active",
  "is_read": false,
  "subject": "<localized: 'A used iPhone 13 is now available in Zagreb'>",
  "message": "<localized: '€420 · Good condition · Zagreb · listed 2 minutes ago'>",
  "channels": ["in_app", "email"],
  "collection": "listings",
  "item": "<listing id>",
  "icon": "bell-ring",
  "action_url": "/<locale>/marketplace/<slug>-<id>",
  "data": {
    "alert_id": "<uuid>",
    "entity_type": "model",
    "entity_id": "<uuid>",
    "matched": { "condition": "good", "city": "Zagreb", "listing_type": "sell" },
    "price": 420,
    "currency": "EUR",
    "source_path": "/catalog/electronics/phones/apple/iphone/iphone-13/used/in-zagreb"
  }
}
```

Notes:

- `action_url` **must** carry the `-{id}` suffix — a bare slug 404s on the product
  route. This is already documented in `app/sitemap.ts`.
- `subject` and `message` are rendered server-side in the alert's stored `locale`,
  from `messages/{locale}/catalogPages.json`, not from the notifier's locale.
- `category: 'alert'` already exists in the `NotificationCategory` union in
  `src/features/notifications/types/index.ts` — no type change needed.
- Web push reuses the existing `web-push` setup and `app/api/push`.

### Throttling and lifecycle

| Rule | Value |
|---|---|
| Minimum gap between notifications for one alert | 24 hours |
| Maximum notifications per alert | 10, then the alert is auto-unsubscribed with a final "we've stopped watching this" message |
| Batch cap per listing | 200 recipients per publish event; the remainder is queued to the next cron tick so one popular model cannot stall the request |
| Status after notifying | stays `confirmed` — an alert is a standing subscription, not a one-shot. `status = 'notified'` is only used for one-shot alerts created with `once: true`. |

---

## 4. Management surfaces

### For the subscriber

- **Signed in**: an "Alerts" tab on `/{locale}/dashboard/favorites`, reusing the
  existing favourites layout. Each row shows the node, the narrowing, how long
  they have been waiting, and how many notifications they have received. Edit
  narrowing, pause, delete.
- **Guest**: every email carries a `token` link to a minimal manage page —
  view, edit max price, unsubscribe. No account required, no login wall.
- **One-click unsubscribe** header (`List-Unsubscribe`) on every alert email.

### For the operator

`/{locale}/dashboard/moderation/catalog-content` gains a **Demand** tab. See
[09-admin-dashboard.md](09-admin-dashboard.md). The core report:

```
Unmet demand — nodes with subscribers and no supply
┌──────────────────────┬───────────┬──────┬───────────┬──────────────┐
│ Node                 │ Narrowing │ Subs │ Listings  │ First asked  │
├──────────────────────┼───────────┼──────┼───────────┼──────────────┤
│ Apple iPhone 13      │ used, Zagreb │  14 │    0     │ 12 days ago  │
│ Samsung Galaxy S22   │ used        │   9 │    0     │  6 days ago  │
│ BMW 3 Series         │ rent, Cairo │   7 │    0     │ 21 days ago  │
└──────────────────────┴───────────┴──────┴───────────┴──────────────┘
```

This is a merchandising work queue: it says precisely which sellers to recruit and
which inventory to chase, sorted by proven demand.

---

## 5. Privacy

`catalog_alerts.email` is PII and is treated as such:

- **Never** returned by any API response, including the operator's demand report —
  which aggregates counts only.
- **Never** logged. Log the alert `id`.
- Public role has **no** permission on `catalog_alerts` at all. Guest rows are
  created by the route handler with the admin token, after rate limiting.
- Authenticated users can read/update/delete only rows where
  `user_id = $CURRENT_USER`, enforced both in the Directus policy **and** in the
  route handler — the app's routes use the admin token and bypass the policy on
  their own.
- Deleting an account cascades its alerts.
- Unconfirmed guest rows are swept after 7 days; unsubscribed rows are hard-deleted
  after 30 days, keeping only an anonymous counter for the demand report.
- The privacy policy needs a short addition covering alert emails and the retention
  windows. That content lives in Directus CMS across all 7 languages, so it must be
  updated there — not in code — and re-applied on prod.

---

## 6. Why this is also an SEO mechanism

Two direct effects:

1. **It makes zero-supply pages defensible.** A page with no inventory that offers
   a real service — explaining the item, showing reference prices, and watching the
   market for you — is a useful search result. A page with no inventory and nothing
   else is thin content. The subscription is what makes the difference substantive
   rather than cosmetic.

2. **It supplies a demand signal the crawler cannot see.** `subscriber_count ≥ 10`
   promotes a below-threshold permutation to indexable
   (see [06 §1](06-seo-structured-data.md)). Ten people asking for "used iPhone 13
   in Zagreb" is direct evidence that the query has volume — better evidence than
   any keyword tool, because it came from people who already searched it and landed
   here.

The loop closes: search brings someone in → the absence is captured as demand →
demand justifies indexing the page → the page ranks better → more demand is
captured → sellers get recruited against a real list → supply arrives → the page
converts.
