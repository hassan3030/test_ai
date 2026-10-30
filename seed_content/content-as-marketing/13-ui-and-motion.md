# 13 — UI & Motion

The visual and motion system for `/catalog/` pages. Direction: **confident but
disciplined** — the pages should feel like a modern product surface, not a
document, while never paying for that feeling with LCP, CLS, or crawlability.

The constraint that shapes everything here: **these are SEO landing pages.** A
fade-in that hides the hero until JavaScript runs is not a design choice, it is a
ranking regression. So motion is layered on in a strict order of cost.

---

## 1. The three-layer motion budget

```
Layer 1 · CSS-only            ~0 KB JS   scroll reveals, hover, focus, marquees
Layer 2 · View Transitions    ~0 KB JS   tier-to-tier navigation
Layer 3 · framer-motion       already bundled  genuinely interactive components
```

Work down the list. Only drop to the next layer when the one above genuinely
cannot express the interaction.

`framer-motion` v12 is already used in **102 files** across the app, so layer 3
costs no new bytes on a page that already loads it — but it does cost hydration
time, and hydration on a landing page competes with LCP. Hence the ordering.

### What must never animate

| Element | Why |
|---|---|
| The `<h1>` | Often the LCP candidate. Must paint at final opacity, immediately. |
| The hero image | The usual LCP element. `priority`, fixed dimensions, no transform. |
| The lede paragraph | Above the fold, and the first thing a reader needs. |
| The stat strip numbers | Count-up animations cause layout shift unless width is reserved — and reserving it means the number is visually wrong for 800 ms. Render the final value. |
| Anything in the first viewport | If it is visible on load, it is already where it belongs. |

Motion begins **below the fold**. That single rule keeps Core Web Vitals clean
and still makes the page feel alive as you scroll.

---

## 2. Layer 1 — CSS scroll-driven animation

Baseline in modern Chromium and Safari, with a graceful no-op elsewhere. Zero
JavaScript, runs on the compositor, cannot block hydration.

```css
/* app/globals.css — or a catalog-scoped stylesheet */

@media (prefers-reduced-motion: no-preference) {
  @supports (animation-timeline: view()) {
    .cm-reveal {
      animation: cm-reveal-in linear both;
      animation-timeline: view();
      animation-range: entry 0% entry 40%;
    }
    /* Stagger children without JS: each child gets its own view() timeline. */
    .cm-reveal-group > * {
      animation: cm-reveal-in linear both;
      animation-timeline: view();
      animation-range: entry 5% entry 45%;
    }
  }
}

@keyframes cm-reveal-in {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: none; }
}
```

Three properties of this approach that matter:

1. **`both` fill mode with a `view()` timeline** means an element already in view
   on load is at its end state — no flash, no reveal-on-load.
2. **Wrapped in `@supports`** so unsupported browsers simply see the content, at
   full opacity, with no JS fallback needed.
3. **Wrapped in `prefers-reduced-motion: no-preference`** so the reduced-motion
   path is the *absence* of the rule, not an override of it.

Applied to sections 5–13 of the page stack (see
[05-page-composition.md](05-page-composition.md)). Sections 1–4 are above the fold
and never carry the class.

### Other layer-1 effects

| Effect | Implementation |
|---|---|
| Child-card hover lift | `transition: transform .18s, box-shadow .18s` + `hover:-translate-y-1` |
| Image zoom on card hover | `overflow-hidden` wrapper + `group-hover:scale-[1.04]` on the image |
| Sticky TOC active state | `scroll-margin-top` on headings + `:target` styling; no observer |
| Comparison strip scroll | native `overflow-x-auto` + `scroll-snap-type: x mandatory` + `scroll-snap-align: start` |
| FAQ expand | native `<details>` + `::details-content` transition with `interpolate-size: allow-keywords` for a height animation, degrading to an instant open |
| Skeleton shimmer | CSS `@keyframes` on a gradient — only for client-side filter results, never initial load |
| Focus ring | `focus-visible:ring-2 ring-offset-2` throughout |

None of these needs a single line of JavaScript.

---

## 3. Layer 2 — View Transitions between tiers

The catalog is a hierarchy people walk up and down: Electronics → Phones → Apple →
iPhone → iPhone 13. Making that navigation feel continuous is the single highest-
value motion investment on these pages, because it is the interaction users repeat.

Next 16 supports the View Transitions API. Wrap the shared elements so the browser
morphs them across navigations:

```tsx
// CatalogChildCard.tsx — the card the user clicks
<Link href={childPath} className="group">
  <div style={{ viewTransitionName: `node-image-${child.id}` }}>
    <Image … />
  </div>
  <h3 style={{ viewTransitionName: `node-title-${child.id}` }}>{child.name}</h3>
</Link>

// CatalogHero.tsx — the destination
<div style={{ viewTransitionName: `node-image-${entity.id}` }}>
  <Image … priority />
</div>
<h1 style={{ viewTransitionName: `node-title-${entity.id}` }}>{content.h1}</h1>
```

Because the `viewTransitionName` is keyed on the entity id, the card image and
title *become* the hero image and `<h1>` — the phone you tapped grows into the
page about it. It reads as one continuous surface rather than a page load.

```css
@media (prefers-reduced-motion: no-preference) {
  ::view-transition-group(*) { animation-duration: .28s; }
  ::view-transition-old(root),
  ::view-transition-new(root) { animation-duration: .2s; }
}
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) { animation: none; }
}
```

Constraints:

- **`viewTransitionName` must be unique per document.** Keying on the entity uuid
  guarantees it. Never key on the tier name alone.
- The breadcrumb gets `viewTransitionName: 'catalog-breadcrumb'` so it stays
  visually anchored while the content below it changes — which is exactly the
  mental model of moving through a hierarchy.
- No polyfill. Browsers without support get an instant navigation, which is fine.

---

## 4. Layer 3 — framer-motion, where it earns its place

Only four components. Each is already a client component for functional reasons,
so the motion adds no new boundary.

| Component | Motion | Why JS is required |
|---|---|---|
| `CatalogListingsSection` | `AnimatePresence` + layout animation as filter results swap | List reconciliation with enter/exit of arbitrary items — CSS cannot track identity |
| `CatalogAlertCard` | Form → success state morph; the "N people waiting" counter easing in after submit | State-driven sequence tied to an async response |
| `CatalogFilterDrawer` (mobile) | Spring slide-in with drag-to-dismiss | Gesture-driven, velocity-aware |
| `CatalogStickyNav` | Slide down when the hero leaves the viewport, active-section underline that slides between items | Position-aware, and the underline needs `layoutId` to travel |

House pattern, matching the existing 102 files:

```tsx
'use client';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';

const shouldReduce = useReducedMotion();
const t = shouldReduce ? { duration: 0 } : { type: 'spring', stiffness: 380, damping: 32 };
```

`useReducedMotion()` is not optional. Every one of these four components reads it.

### Explicitly rejected

| Idea | Why not |
|---|---|
| Parallax hero | Moves the LCP element; costs a scroll listener on every catalog page |
| Count-up stat numbers | CLS or a visually wrong number for ~800 ms, on the most trusted data on the page |
| Staggered cascade on the child grid above the fold | Delays the first meaningful paint of the page's primary navigation |
| Page-transition curtain overlays | Blocks content for the duration; View Transitions achieve more for free |
| Magnetic / cursor-following hover | Desktop-only flourish, `mousemove` handler per card, invisible on the touch traffic that dominates |
| Animated gradient backgrounds | Continuous compositor work on a page people read for two minutes |
| Scroll-jacked section snapping | Fights the browser, breaks anchor links from the TOC, hostile with a keyboard |

Each of these would make a demo more impressive and the product worse.

---

## 5. Visual system

Tailwind v4 is configured via `@tailwindcss/postcss`, and `next-themes` already
handles light/dark. These pages introduce **no new design tokens** — they compose
existing ones so the catalog feels continuous with the marketplace.

### Layout

Repeated from [05 §3](05-page-composition.md) as the implementation reference:

| Token | Value |
|---|---|
| Container | `mx-auto w-full max-w-[1440px] px-4 sm:px-6 lg:px-8` |
| Grid | `grid grid-cols-4 md:grid-cols-8 xl:grid-cols-12 gap-6 xl:gap-8` |
| Content / rail | `xl:col-span-8` / `xl:col-span-4 xl:sticky xl:top-24 self-start` |
| Section rhythm | `py-10 lg:py-14` |
| Child grid | `grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6` |
| Body measure | `max-w-[68ch]`, `text-[17px] leading-[1.7]` |

### Typographic scale

Landing pages need a wider range than dense app UI — the H1 is a headline, not a
page title.

| Role | Classes |
|---|---|
| H1 | `text-3xl lg:text-5xl font-semibold tracking-tight text-balance` |
| Lede | `text-lg lg:text-xl leading-relaxed text-muted-foreground text-pretty` |
| H2 | `text-xl lg:text-2xl font-semibold tracking-tight` |
| H3 | `text-base lg:text-lg font-semibold` |
| Body | `text-[17px] leading-[1.7]` |
| Caption / meta | `text-sm text-muted-foreground` |
| Numeric (prices, counts) | `tabular-nums font-medium` |

`text-balance` on the H1 and `text-pretty` on the lede matter more than usual here:
titles are generated per node in seven languages, so line breaks cannot be
hand-tuned.

### Depth and surface

One elevation step, used consistently:

```
Page background        bg-background
Card / section surface bg-card border border-border rounded-2xl
Hover                  shadow-md -translate-y-1
Sticky rail            bg-card/80 backdrop-blur-sm border
Emphasis panel         bg-muted/50   (price guidance, notify-me)
```

No nested cards. A card inside a card is the visual signature of a page assembled
by a template rather than designed.

### The stat strip

The most-looked-at component on the page, and the one that must earn trust.

```
┌────────────┬──────────────┬──────────┬──────────────────┐
│    24      │  €320–590    │    7     │  Used · New      │
│ listings   │  price range │  cities  │  conditions      │
└────────────┴──────────────┴──────────┴──────────────────┘
```

- `tabular-nums` so digits do not jitter between locales.
- Every cell is a link — to the sorted grid, to the city cluster, to the condition
  pages. Free internal linking from the element people look at first.
- Numbers render at their final value. No count-up.
- Prices wrapped `dir="ltr"` so they stay readable inside RTL text.
- At zero supply the strip is replaced entirely rather than showing four zeros —
  four zeros reads as a broken page.

---

## 6. RTL

`localeConfig[locale].direction` already exists and the `[locale]` layout sets
`dir`. For these components:

- **Logical properties only.** `ps-*`/`pe-*`, `ms-*`/`me-*`, `text-start`,
  `border-s`, `start-0`/`end-0`. Never `pl-*`, `text-left`, `left-0`.
  Verified by grep in [11 §12](11-verification.md).
- Reveal animations translate on the **Y axis only**, so they need no mirroring.
- Horizontal scrollers (comparison strip) mirror automatically with `dir`; scroll
  snap works unchanged.
- The View Transition morph is position-based and mirrors for free.
- Arabic needs more leading: `[dir=rtl]:leading-[1.85]`.
- Chevrons and arrows use `rtl:rotate-180` or a logical icon swap.

---

## 7. Accessibility

Motion-specific requirements on top of the general list in
[05 §3](05-page-composition.md):

- Every animation sits behind `prefers-reduced-motion: no-preference`, or reads
  `useReducedMotion()`. The reduced-motion path is content at final state,
  instantly — never a slowed-down version.
- No animation loops indefinitely in the viewport.
- Nothing flashes more than three times per second.
- Scroll-driven reveals never gate content behind scrolling for assistive tech —
  the content is in the DOM at full opacity as far as a screen reader is concerned.
- The sticky nav must not trap focus, and must not cover a focused element:
  `scroll-margin-top` on every heading accounts for its height.
- Drag-to-dismiss on the mobile filter drawer has a visible close button as an
  equal-weight alternative.

---

## 8. Performance guardrails

| Guardrail | Enforcement |
|---|---|
| Animate only `transform` and `opacity` | Review rule. Never `height`, `top`, `width`, `margin`. |
| No `will-change` left permanently on | Only inside `:hover`/`:focus-visible`, never on a static class |
| No scroll or `mousemove` listeners on catalog pages | Layer 1 and 2 make them unnecessary; layer 3's four components use none |
| Hero image `priority`, everything else lazy | `next/image` defaults + explicit `priority` on hero only |
| Every image has `width`/`height` or `fill` with a sized parent | CLS target 0 |
| Fonts do not shift text | `next/font` with `display: swap` and a matched fallback metric |
| JS added by this feature | Measure before/after with `next build` output. Target: no increase over the marketplace page. |

The budget from [04 §8](04-rendering-caching.md) still governs: LCP < 2.5 s,
CLS < 0.1, TBT < 200 ms, Lighthouse desktop ≥ 90. If a motion idea threatens any
of those, the motion loses — these pages exist to rank.

---

## 9. Component-by-component motion map

| # | Section | Layer | Motion |
|---|---|---|---|
| 1 | Breadcrumb | 2 | `viewTransitionName: 'catalog-breadcrumb'`, stays anchored across navigation |
| 2 | Hero | 2 | image + H1 morph in from the card that was clicked. **No entrance animation.** |
| 3 | Child grid | 1 | hover lift + image zoom; `cm-reveal-group` only if the grid starts below the fold |
| 4 | Live listings | 1 + 3 | cards reveal on scroll; `AnimatePresence` on filter change |
| 5 | Editorial body | 1 | `cm-reveal` per `<h2>` block; TOC active state via `:target` |
| 6 | Buying guide | 1 | `cm-reveal` |
| 7 | Key specs | 1 | `cm-reveal`; row hover highlight |
| 8 | Price guidance | 1 | `cm-reveal`; condition bar segments grow from 0 width on entry via `view()` |
| 9 | Comparison strip | 1 | scroll-snap; hover lift |
| 10 | FAQ | 1 | native `<details>` height transition |
| 11 | Modifier cluster | 1 | `cm-reveal-group` staggers the chips |
| 12 | Related links | 1 | `cm-reveal` |
| 13 | Notify-me card | 3 | form → success morph; waiting-count fade-in after response |
| — | Sticky sub-nav | 3 | slide down past the hero; `layoutId` underline slides between sections |
| — | Mobile filter drawer | 3 | spring slide + drag-to-dismiss |

Eleven of fifteen are pure CSS. Two are View Transitions. Four use
framer-motion — and all four are components that had to be client components
anyway.

---

## 10. Definition of done

- [ ] Above-the-fold content paints at final opacity with JS disabled
- [ ] `curl` output contains the H1, lede and body text (see [11 §2](11-verification.md))
- [ ] `prefers-reduced-motion: reduce` produces a fully static, fully usable page
- [ ] No `height`/`top`/`width` in any `transition` or `@keyframes`
- [ ] No scroll or `mousemove` listener added by this feature
- [ ] Lighthouse desktop ≥ 90 performance, ≥ 95 a11y, 100 SEO, on all five tiers
- [ ] CLS = 0 on first load, measured with throttling on
- [ ] View Transition morph works card → hero on every tier, and degrades to an
      instant navigation where unsupported
- [ ] RTL verified on `/ar/catalog/…`: no `pl-*`/`text-left`, no horizontal page scroll
- [ ] Bundle size on a catalog page ≤ the marketplace page
