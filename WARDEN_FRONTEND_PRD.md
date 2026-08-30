# Project Warden — Frontend PRD

## What this project is

Warden is a security layer for AI-agent-to-AI-agent payments. When a buyer
agent negotiates a purchase with a merchant agent, existing payment protocols
can prove a transaction was *signed* — not that the buyer's agreement to pay
was *honestly obtained*. A merchant agent could hide a hostile instruction in
its messages, or slowly manipulate the buyer agent into a purchase it was
never authorized to make.

Warden watches the negotiation, checks it against three signals (spending
rules, sudden manipulation, gradual manipulation), and only lets a payment
through if the negotiation was clean. If something's wrong, it blocks the
payment or pauses it for a human to approve.

Built for Razorpay's AI Buildathon, Track 02 (AI Risk Manager). **The backend
is done and fully live** — this PRD is for the frontend only.

## Hero background image — FINAL, locked

The hero background is final. File: `scene.png`, saved at repo root. Do not
regenerate, do not treat this as a placeholder.

**Composition (load-bearing for layout — read before building the hero):**
- Left ~60% of the frame is a flat, matte, uncluttered wall — warm amber/
  orange, soft ambient shadow gradient, no texture, no cracks, no objects
  mounted on it, no figures. **This is where the glass console panel goes.**
  Anchor the hero panel (transcript, trust score, verdict badge, arrow nav)
  to this left/center-left zone.
- Right ~40% of the frame carries all the scene's life: a red-shopfront
  barbershop with two figures mid-haircut, two seated men on the sidewalk,
  a loaded vegetable cart, a banana-leaf tree, a parked rickshaw. **Do not
  place UI elements over this zone** — no arrow nav, no corner labels,
  nothing. It needs to stay fully visible; it's doing the "this is a real
  place" work that the empty wall can't do alone.
- Sky occupies roughly the top third on the left side, giving extra vertical
  room above the wall if the panel needs to breathe upward (e.g. the
  oversized verdict word rendering above the main panel).
- The image is a single wide (roughly 16:9) full-bleed illustration. Apply
  the `brightness(0.85) saturate(0.9)` filter and per-verdict color-wash
  overlay specified in the Motion section — test that the wash is visible
  against this specific palette (warm orange/amber base) rather than
  assuming it reads the same as it would on a neutral gray.
- Because the left zone is intentionally plain, the glass panel's own
  presence (blur, border, shadow, glow) is what gives that side of the
  frame its visual interest — don't under-style the panel thinking the
  background will carry it. This is the one place the glassmorphism recipe
  has to do real work, not just decorate.

## Backend is real — build against it, don't fake it

Every data point below comes from a working API, already running locally with
zero CORS friction (FastAPI serves `ui/` as static files, same-origin). There
is no placeholder data in this project. 40 real labeled runs exist on disk.

- `GET /scenarios` — list of available negotiation scenarios
- `POST /negotiate` — runs a negotiation, returns `tx_id`, `verdict`
  (PASS/STEPUP/REJECT), `explanation`, `trust_score_trajectory`
- `GET /transcripts/{tx_id}` — full turn-by-turn transcript array
- `GET /verdicts/{tx_id}` — full verdict + signal bundle (violations, drift
  detail, injection flags, cart total)
- `POST /stepup/{tx_id}/resume` — send `{"approved": true|false}`, get back
  final verdict
- `POST /policy/swap` — send `{"policy_name": "quick_commerce"|"b2b_receivables"}`,
  get back re-scored verdicts for all stored transactions, no LLM calls, near
  instant
- `GET /selfplay/report` — real precision/recall/F1/FPR numbers

40 pre-run examples exist: `eval_clean_0..9`, `eval_legitimate-revision_0..9`,
`eval_injected_0..9`, `eval_gradual-drift_0..9`. Pick one strong representative
`tx_id` per class up front (test them, make sure the transcript reads well)
and hardcode those four IDs as the hero's default cases. Fetch their real
transcript + verdict data on page load. Do not invent dialogue — it already
exists and is better than anything invented.

## Tech stack

Plain HTML/CSS/JS. No framework, no build step. Fits the existing `ui/`
static-file setup exactly. GSAP via CDN for animation sequencing (its
easing and stagger/timeline control is meaningfully better than raw CSS
for the choreography specced below — use it, don't hand-roll requestAnimationFrame
loops). Chart.js or a hand-drawn SVG path (see trust line below) for the graph.

## Visual system — exact spec, not vibes

### Color palette

```
--void:        #05060a   /* page background, negative space */
--panel-bg:    rgba(18, 22, 30, 0.55)   /* glass panel fill */
--panel-border: rgba(255, 255, 255, 0.08)
--panel-blur:  18px

--ink:         #f2ede4   /* primary text, warm off-white, NOT pure white */
--ink-dim:     rgba(242, 237, 228, 0.6)

--pass:        #10b981   /* emerald — clean/legit */
--pass-glow:   rgba(16, 185, 129, 0.35)
--reject:      #ef4444   /* crimson — injection */
--reject-glow: rgba(239, 68, 68, 0.4)
--stepup:      #f59e0b   /* amber — drift */
--stepup-glow: rgba(245, 158, 11, 0.35)

--accent-blue: #3b82f6   /* cognition/data accents, sparingly */
```

Every verdict state has ONE color that touches: the badge, the trust-line
stroke, the panel's border glow, and the arrow-nav active dot. Nothing else
in the UI should carry that color at that moment — this is how the palette
reads as intentional instead of decorative.

### Glassmorphism — exact recipe, use everywhere a panel sits over the hero image

```css
background: var(--panel-bg);
backdrop-filter: blur(var(--panel-blur)) saturate(140%);
-webkit-backdrop-filter: blur(var(--panel-blur)) saturate(140%);
border: 1px solid var(--panel-border);
border-radius: 20px;
box-shadow:
  0 8px 32px rgba(0, 0, 0, 0.4),
  inset 0 1px 0 rgba(255, 255, 255, 0.06);
```

The verdict badge additionally gets a colored glow using the active state's
`-glow` variable: `box-shadow: 0 0 24px var(--pass-glow)` (swap per state),
transitioning over 400ms when the verdict changes.

Do NOT apply glass panels to the sections below the hero (architecture,
eval) — those sit on solid `--void` or a subtle dark texture, no blur. Glass
is reserved for the hero, where it's doing the job of "console floating over
a real place." Using it everywhere flattens that distinction.

### Typography

- Display/headline font: something with real character — a serif with
  presence (e.g. "Fraunces" or "Playfair Display") or a distinctive
  condensed sans (e.g. "Space Grotesk") for the verdict word (PASS / REJECT
  / STEPUP) rendered large. Pick ONE and commit — don't mix display fonts.
- Body/UI font: "Inter" or "IBM Plex Sans" for transcript text, labels,
  numbers — needs to stay legible at small sizes in a glass panel over a
  busy image.
- The verdict word itself (PASS/REJECT/STEPUP) should render oversized
  (60-80px+) as a hero moment, not just a small badge label — this is the
  single word a judge should read from across a room.

### Motion — every transition specified, not left to "animate it"

**Arrow navigation (case switching):**
1. Outgoing transcript panel: fade + slide out 24px to the left, 250ms,
   ease `power2.in`
2. Incoming transcript panel: fade + slide in from 24px right, 300ms,
   ease `power2.out`, starts 100ms after outgoing begins (slight overlap,
   not a dead gap)
3. Trust score number: animate via GSAP `textContent` tween counting from
   old value to new value over 500ms — never a hard cut
4. Verdict badge: color and glow cross-fade over 400ms; if the verdict word
   itself changes, it scales from 0.9→1.0 with a slight overshoot
   (`back.out(1.4)`) while fading in, 350ms
5. Detector badges (Ed25519/Constraint/Drift/Injection): stagger in
   individually, 60ms apart, each a simple fade+rise of 8px

**Trust score line (the emotional centerpiece, especially on Drift):**
- Render as an SVG path. Animate its `stroke-dashoffset` from full length
  to 0 over 1200ms, `power1.inOut` easing, so the line visibly *draws
  itself* left to right rather than appearing instantly
- The danger threshold (0.45 or policy-specific value) renders as a static
  dashed horizontal line, present before the trust line draws, so the
  audience sees the line approach and cross it
- On Drift specifically: the point where the trust line crosses the
  threshold gets a small pulse/ping animation (one-shot, not looping) the
  moment the draw animation reaches that x-position — this is the "there it
  is" beat
- Line color = the active verdict color (emerald for Clean/Legit, crimson
  reaching down for Injection if shown, amber for Drift)

**On page load:**
- Hero background image fades in from black, 800ms
- Glass panels rise in with a 12px translateY + fade, staggered 80ms each,
  starting 400ms after the background begins (image establishes the scene
  before UI appears on top of it)

**Scroll-triggered (sections below hero):**
- Each section's content fades + rises in (16px) as it enters viewport,
  using IntersectionObserver — not on every scroll tick, one-shot per
  section
- Numbers in the evaluation stat row (precision/recall/F1/FPR) count up
  from 0 when that section enters view

**Hover/interactive states:**
- Arrow nav buttons: scale 1.0→1.08 on hover, 150ms, plus the glass panel
  brightens slightly (`background` lightens ~5%)
- Policy toggle and STEPUP approve/reject buttons: same scale treatment,
  plus their border color shifts toward the relevant verdict color on hover
  (approve → hint of emerald, reject → hint of crimson) so intent is legible
  before the click

**Global rule:** wrap all of the above in a check for
`prefers-reduced-motion: reduce` — cut durations to near-zero and drop the
non-essential flourishes (overshoot, pulse-ping, parallax) for that case,
but keep state changes instant and correct.

### Background scene treatment

The hero image sits as a fixed full-bleed layer behind everything, with a
subtle parallax: on mouse move (desktop) or device tilt (mobile, if easy to
wire), the image shifts max ~8px opposite the cursor — barely perceptible,
adds depth without being gimmicky. Apply a slight `filter: brightness(0.85)
saturate(0.9)` permanently so glass panels stay legible on top of it, then
layer a subtle color-grade overlay per verdict state (a low-opacity color
wash matching the active `-glow` variable, ~6% opacity) so the *scene itself*
subtly shifts mood as the verdict changes, not just the panels on top of it.

## Page structure

### Hero section (top of page, always visible on load)

One fixed layout, one consistent background scene (nostalgic illustrated
Indian-street style, à la saloon.wtf — image provided separately, see below).
The layout does not change between cases. Only the content inside it does.

Shows ONE case at a time:
- **Transcript panel** — real turn-by-turn dialogue from the fetched
  transcript (speaker, message). Keep it readable, don't over-truncate.
- **Trust score display** — a line/graph of `trust_score_trajectory`,
  animated in. Most visually important on the Drift case, where it should
  read as a clear, steady decline crossing a visible danger line late in
  the sequence — not a random jagged mess.
- **Verdict panel** — pulled from the verdict object: Ed25519 status,
  ConstraintChecker (violations array), DriftScorer (sudden_drop /
  gradual_drift / coherence_break), InjectionScanner (injection_flags), and
  the final verdict (PASS / STEPUP / REJECT) as a clearly colored badge.

**Navigation**: left/right arrows (click or arrow keys) cycle through the
four cases in this fixed order:

**Clean → Legit → Injection → Drift**

Each arrow press swaps transcript, trust score, and verdict panel content
with a smooth transition. Background and layout stay constant — this is one
scene changing state, not four different pages.

**Drift case special handling**: when landed on, the verdict should read
STEPUP and the trust line should visibly cross the danger threshold near the
end of its trajectory. Do not add live Approve/Reject buttons in the
flip-through hero — that's a deeper interaction, out of scope for the arrow
flow (see Policy & STEPUP section below for where that belongs).

### Below the hero — scrollable sections

1. **Architecture** — short explanation of the pipeline: Buyer ↔ Merchant
   negotiation → Ed25519 signature gate → three parallel detectors
   (ConstraintChecker, DriftScorer, InjectionScanner) → policy decision →
   PASS / STEPUP / REJECT. Visual diagram, not a wall of text. Mention in
   passing (one sentence, no dedicated interactive screen) that a tampered
   or invalid signature is rejected before any detector even runs — this is
   real backend behavior (`signature_gate`), just not something you need to
   build an interactive demo for.

2. **Policy comparison** — this is a real, cheap feature, build it for real.
   A small control lets the visitor re-evaluate the currently-displayed case
   under a different policy (`quick_commerce` vs `b2b_receivables`) by
   calling `POST /policy/swap`. Show the verdict changing (or not changing)
   without re-running the negotiation. Use language like "same negotiation,
   same signals, different policy" — this is the single best proof that
   detection and policy are separate systems. Keep this UI light: a toggle
   or two buttons, not a full dashboard.

3. **STEPUP / human review demo** — a dedicated small section (separate
   from the hero) showing the real approve/reject flow. Pick one drift case,
   show its STEPUP state, and wire real buttons to `POST
   /stepup/{tx_id}/resume`. Show the returned verdict and explanation after
   the click. This is your strongest "judgment, not just pattern-matching"
   moment — give it space, just not inside the hero's arrow flow.

4. **Evaluation proof** — real numbers from `/selfplay/report`: precision,
   recall, F1, FPR, all currently 1.0/1.0/1.0/0.0%. Present as evidence, not
   marketing copy — a clean stat row plus a short breakdown by class (10
   clean, 10 legit, 10 injected, 10 drift).

5. **Defense-only statement** — one short, plain paragraph: adversarial
   self-play (AttackerAgent) is closed, offline, and used only to harden
   detection internally. Never exposed as a callable capability, never
   targets anything outside the project.

## Non-negotiables checklist (for the coding agent to self-check against)

- [ ] Every color used maps to the palette above — no ad-hoc hex values
- [ ] Glass recipe applied exactly as specified, hero only
- [ ] Verdict word renders oversized as a hero moment, correct display font
- [ ] Arrow nav transition matches the 5-step sequence above, not a generic fade
- [ ] Trust line self-draws via stroke-dashoffset, doesn't just appear
- [ ] Drift threshold-cross gets its one-shot pulse
- [ ] Numbers (trust score, eval stats) count/tween, never hard-cut
- [ ] `prefers-reduced-motion` respected throughout
- [ ] Sections below hero are NOT glass — solid/textured dark background only

## Explicitly out of scope

- No tamper-check interactive demo (no backend endpoint for it — mention it
  in the architecture section as a sentence, nothing more)
- No cognition/reasoning drawer per turn
- No presenter mode, debug controls, narration toggles, keyboard shortcut
  layer beyond arrow-left/arrow-right on the hero
- No separate "scenario" screens beyond what's described above — everything
  lives on one scrollable page

## Design direction

Nostalgic, illustrated, warm — reference is saloon.wtf, realized in
`scene.png` (see above). One consistent hero scene, not a different
background per section. Let color signal danger vs. safety (calm tones for
Clean/Legit, sharp red/crimson accents for Injection, amber tension for
Drift/STEPUP) rather than swapping the whole visual environment. Below the
hero, sections can shift to a darker, more neutral tone appropriate for
evidence/data (architecture, eval) without breaking continuity — think "the
warmth recedes as the content gets more technical," not four unrelated
moods.
