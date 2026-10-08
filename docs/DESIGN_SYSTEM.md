# Seller workspace design system

## Audit, in priority order

- **P0 — No browser interface:** the repository had API endpoints and Messenger messages, but no HTML components, CSS, visual tokens, or browser interaction states. The seller could not inspect orders or inventory without operational tools.
- **P0 — No authenticated read model:** existing mutations were protected, but there was no safe dashboard data endpoint. A public interface must never embed customer data or credentials.
- **P1 — No common visual language:** spacing, typography, color, radii, elevation, and motion were undefined for the web. Messenger appearance is controlled by Meta and cannot share browser CSS.
- **P1 — No web accessibility or responsive baseline:** keyboard navigation, focus, touch targets, empty/error/loading states, and both themes needed a shared implementation.
- **P2 — No browser verification:** the existing Python tests covered service behavior, not presentation or interaction.

## Direction

The seller workspace uses warm ivory, charcoal ink, and copper with champagne highlights. Slate-blue success and lavender information badges replace all green accents. Editorial headings and an abstract flowing hero distinguish the brand while operational panels stay calm and legible. A persistent preview label separates sample data from a connected shop.

The real ShaderGradient effect runs in an isolated React Three Fiber island. The rest of the workspace uses native controls and ES modules. Glass appears in the hero reporting controls and searchable command dialog, using CSS backdrop blur and substantial surface opacity. Native buttons, keyboard focus, and modal semantics are retained; no whole-page screenshot/refraction library is imported.

## Foundations

The source of truth is `src/tindabot/web/tokens.css`. All shared visual decisions belong there; chart geometry, percentages, viewport breakpoints, and optical icon coordinates are structural values.

- **Type:** system sans-serif for operational content and Georgia for editorial headings; a 52px display token extends the 12, 14, 16, 20, 25, 31, 39px scale. Body line-height 1.6, headings 1.15 with tight tracking. Numeric data uses tabular figures. Both font stacks are local, with no external font request.
- **Spacing:** 4px base; 4, 8, 12, 16, 20, 24, 32, 40, 48, 64px steps. Controls use 12–16px horizontal padding, panels 24px, page gutters 40px on desktop and 16px on mobile.
- **Color:** warm neutral scale with semantic copper, slate, lavender, amber, and red aliases. Light surfaces are ivory and white; dark surfaces are plum-charcoal. Text, chart, focus, selection, and status colors support both themes.
- **Shape:** 4, 8, 12, 16px radii; large panels contain smaller controls. Pills distinguish status labels, the search field, and floating reporting controls.
- **Depth:** flat, surface, floating, modal. Hairline borders carry most separation; dark elevation comes primarily from lighter surfaces.
- **Icons:** one local outline SVG vocabulary with 24px view boxes, 1.7px strokes, and round line caps. No icon font or external image dependency.

## Shared components and behavior

Buttons, navigation items, fields, selects, status badges, metric strips, data tables, empty states, toasts, skeletons, and native dialogs share tokens and state rules. All buttons and form controls have at least 44px hit areas. Text wraps or truncates within constrained containers. Mobile order tables retain customer, status, and amount together; wider auxiliary tables can scroll within their own region.

| Component | State behavior |
| --- | --- |
| Button / nav | Default, subtle hover, visible focus, .97 press scale, disabled; pending actions use explicit text and prevent repeated submission. |
| Field / select | Native semantics, clear labels, focus ring, inline validation/error descriptions; credentials remain in memory only. |
| Table / inventory | Loading skeleton matches rows; empty search offers clear filters; empty connected shop explains the next step; request failure offers retry. |
| Order drawer | Native modal focus containment, Escape and close control, return focus to opener; version-checked writes with inline failure and success toast. |
| Stock / automation | Explicit save; server confirmation before changing live state. Preview changes are local and labeled. |
| Theme | Immediate local preference with accessible action label; safe optimistic change. |

## Motion specifications

| Trigger | Motion | Duration / easing |
| --- | --- | --- |
| Control hover / press | Transform only; subtle lift / .97 scale | 140ms / ease-out |
| Theme switch | Instant colors; no page-wide repaint animation | Instant |
| View change | Parent opacity and 8px vertical translation; grouped metrics follow at 40ms offsets | 320ms / ease-out |
| Detail open | Drawer enters from the right; backdrop fades | 240ms / ease-out |
| Dialog / toast enter | Opacity and 8px translation | 240ms / ease-out |
| Toast exit | Opacity and 4px translation | 160ms / ease-in |
| Loading | Single restrained skeleton sweep per data request | 500ms / ease-out |
| Number refresh | Whole metric group fades in; no counting through misleading intermediate amounts | 240ms / ease-out |
| Shader background | Slow copper/champagne water-plane shader, no pointer capture | GPU render loop while visible and enabled; DPR capped at 1 |
| Inventory / action hover | Small vertical lift or directional arrow movement | 240ms / ease-out |
| Chart exploration | Readout and crosshair follow the selected day without interpolation | Immediate, pointer or native keyboard slider |
| Quick actions | Searchable native dialog with arrow-key navigation | 240ms / ease-out, Ctrl/Cmd+K or header button |

Reduced motion removes movement and uses immediate state changes. The ambient effect has a persistent pause/play control; it stops rendering offscreen or in a hidden tab. Mobile widths (760px and below), reduced motion, data saver, and unsupported WebGL skip the graphics download entirely on initial load. The static gradient and linework keep the same composition. An already loaded desktop canvas pauses on resize or preference changes; navigation disposes it, and in-view refreshes preserve the same context. Context loss reveals the static fallback.

`studio.css` contains the visual layer, `motion.js` owns visibility/preferences, and `frontend/hero.jsx` owns the optional React island. Run `npm run build:effects` before packaging source changes. Local, compressed assets require no external fonts, textures, HDR files, or client CDN connections. The optional desktop effect is approximately 1.39 MB minified / 360 KB gzip; the sampled mobile resource transfer is approximately 35 KB because that bundle is skipped. These are build/local measurements, not hosted network guarantees. Financial and stock changes wait for confirmation. The compact hero presents a live pending-order briefing and quick actions. A charcoal priority panel separates follow-up tasks from the chart. Order sorting preserves filtering and keyboard focus; the order pipeline filters by fulfillment stage and explicitly counts only loaded records. Search can be cleared without losing the selected status, and changing workspace sections resets the search.

On mobile, persistent bottom navigation respects safe-area insets and the order table groups customer names under order numbers, keeping status and amount visible at 320px without horizontal scrolling. The order drawer shows the current fulfillment stage, total, and placement date; previous/next controls review the current filtered queue without closing the drawer. Product monograms are decorative identifiers, not invented product photographs.

## Verification

Reviewed 4 October 2026. The original repository contained no web interface; the implementation adds a seller workspace rather than reskinning nonexistent components.

| Self-review question | Result and evidence |
| --- | --- |
| Is every value from a token? | Shared color, type, spacing, radius, elevation, and motion foundations are tokenized. Structural breakpoints, chart geometry, icon paths, hairline widths, and a few layout dimensions remain literal values; the implementation does not claim every CSS number is a token. |
| Does motion have a purpose and respect reduced motion? | Press feedback, view/drawer entry, loading, and confirmation feedback use transform/opacity. The optional shader has pause, visibility, reduced-motion, and fallback controls. Browser tests instrument real WebGL draw calls to verify rendering and pause behavior, plus refresh preservation, disposal, and context loss. |
| Are interaction states complete? | Implemented focus, hover, press, disabled, loading, empty, error, and success patterns. Browser workflows cover real interactions, native dialog dismissal/focus return, retry errors, and idempotent write payloads. |
| Does contrast hold up in both modes? | Automated axe A/AA checks pass on the tested overview, connection dialog, order detail, inventory, and automation views. Light/dark screenshots were visually reviewed. Automated checks are not a full screen-reader or accessibility certification. |
| Is mobile usable? | 390px viewports cover every view and 44px controls; 320px overflow is also tested. The header and chart were adjusted after visual review. Mobile order tables fit without horizontal scrolling, and bottom navigation stays reachable after scrolling. |
| Is physical mobile performance verified? | No. A local Chromium sample at 390×844 with 4x CPU slowdown is recorded in `validation/workspace-performance.json`. The latest measurement is recorded with its raw timings and transferred resource size. Mobile skips the optional graphics bundle. Interaction measurement includes automation overhead; the desktop shader test uses software WebGL and establishes behavior, not hardware frame rate. Hardware, network, sustained FPS, Safari, and Firefox acceptance remain external checks. |
| Is this ready for professional review? | Yes as a coherent staging candidate: restrained surfaces, a common icon vocabulary, clear hierarchy, and explicit preview/live boundaries. Production approval still depends on real seller/provider acceptance and the release gates in `DEPLOYMENT.md`; aesthetic quality is a review judgment rather than a test result. |

Validation artifacts: `validation/workspace-light.png`, `validation/workspace-dark.png`, `validation/workspace-mobile.png`, `validation/workspace-orders.png`, `validation/workspace-order-drawer.png`, `validation/ui-tests.json`, and `validation/workspace-performance.json`. Run `npm run build:effects` then `npm run test:ui` to reproduce browser checks. The in-app browser execution tool was unavailable, so these checks use local headless Playwright/Chromium.


## Feature refinement, 7 October 2026

Orders combine independent fulfillment and payment filters. Payment labels remain visible with amounts on mobile, and CSV exports include payment status. Inventory supports empty-shelf and inactive views, name/stock/price sorting, and a live adjustment estimate with keyboard-accessible shortcuts. The automation screen pairs its settings with a snapshot summary and a conditional checklist; uncertain deliveries are distinct from failed incoming events and failed outbound jobs. These diagnostics describe observed state, not a claim that all integrations are healthy.

Orders now defaults to All dates, with Needs attention and Reporting period scopes. Connected search and filters operate on the server, Load more orders retrieves subsequent pages, and CSV exports retrieve the whole selected result set. Pending counts cover all dates independently of financial charts. Back/Forward and section returns retain working context in tab memory; credentials and customer searches are excluded from persistent storage and browser history. Order-code targets remain at least 44 pixels wide, including shorter legacy codes.

See `FEATURE_REVIEW.md` for findings, completed changes, and the remaining feature priorities.
