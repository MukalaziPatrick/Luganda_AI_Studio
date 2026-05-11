# Warm Editorial Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved Warm Editorial design system (terracotta + cream palette, editorial typography, mobile component fixes) to the Luganda AI Studio frontend.

**Architecture:** Token replacement already done in `styles.css`. Remaining work is 4 mobile CSS overrides and one meta tag update in `index.html`. All other pages inherit tokens automatically.

**Tech Stack:** Static HTML/CSS — no build step, no JS changes.

---

## Status Check (as of plan creation)

The following are ALREADY done (no action needed):
- `:root` light-mode tokens — terracotta + cream ✅
- `[data-theme="dark"]` tokens — warm dark brown ✅
- Hero title `clamp(2.4rem, 9vw, 3.2rem)` ✅
- `.hero-cta { width: 100% }` on mobile ✅
- Feature cards `border-left: 4px solid var(--lime)` ✅
- Feature cards `box-shadow: none` ✅
- Stats row 4-column inset box ✅
- Bottom nav active pill `var(--lime-bg)` ✅
- All mobile responsive breakpoints ✅

---

## Task 1: Fix mobile btn-primary border-radius

**Files:**
- Modify: `frontend/styles.css` — `@media (max-width: 768px)` `.btn-primary` block

The spec requires `border-radius: 8px` (editorial, not pill) for `.btn-primary` on mobile.

- [ ] **Step 1: Edit styles.css — add border-radius override**

In `@media (max-width: 768px)`, find the `.btn-primary` rule (around line 789):
```css
  .btn-primary   { padding: 12px 20px; font-size: 14px; min-height: 44px; }
```
Change to:
```css
  .btn-primary   { padding: 12px 20px; font-size: 14px; min-height: 44px; border-radius: var(--radius-sm); }
```

- [ ] **Step 2: Verify**

Open `http://127.0.0.1:8000/app/index.html` on a 375px viewport. The "Start Translating →" button should have squared-off corners (8px radius), not a pill shape.

---

## Task 2: Fix hero-desc font-size on mobile

**Files:**
- Modify: `frontend/styles.css` — `@media (max-width: 768px)` hero block

Spec: `.hero-desc` → `0.88rem` on mobile. Currently overridden to `0.95rem` at 768px.

- [ ] **Step 1: Edit styles.css**

In `@media (max-width: 768px)`, find:
```css
  .hero-desc    { font-size: 0.95rem; margin-bottom: 20px; max-width: 100%; }
```
Change to:
```css
  .hero-desc    { font-size: 0.88rem; margin-bottom: 20px; max-width: 100%; }
```

- [ ] **Step 2: Verify**

Hero description text should be visibly smaller than the title and clearly subordinate.

---

## Task 3: Fix stat-value size on mobile

**Files:**
- Modify: `frontend/styles.css` — `@media (max-width: 768px)` stats block

Spec: `.stat-value` → `1.5rem` on mobile. Currently overridden to `1.4rem`.

- [ ] **Step 1: Edit styles.css**

In `@media (max-width: 768px)`, find:
```css
  .stat-value { font-size: 1.4rem; }
```
Change to:
```css
  .stat-value { font-size: 1.5rem; }
```

- [ ] **Step 2: Verify**

Stats numbers should be visually prominent on mobile.

---

## Task 4: Fix feature-card padding on mobile (preserve left stripe)

**Files:**
- Modify: `frontend/styles.css` — `@media (max-width: 768px)` feature-card block

Spec: `padding: 18px 16px 18px 20px` — extra left padding makes room for the 4px terracotta stripe so text doesn't crowd it.

- [ ] **Step 1: Edit styles.css**

In `@media (max-width: 768px)`, find:
```css
  .feature-card       { padding: 16px; min-height: 90px; }
```
Change to:
```css
  .feature-card       { padding: 18px 16px 18px 20px; min-height: 90px; }
```

Also update the tiny phone override in `@media (max-width: 374px)`:
```css
  .feature-card { padding: 14px; }
```
Change to:
```css
  .feature-card { padding: 14px 12px 14px 18px; }
```

- [ ] **Step 2: Verify**

Feature cards should show a clear left terracotta stripe with readable text not crowding the border.

---

## Task 5: Update theme-color meta tag in index.html

**Files:**
- Modify: `frontend/index.html` — `<meta name="theme-color">` tag

The theme-color meta still references the old `#E8E6DE` beige. Update to new cream bg.

- [ ] **Step 1: Edit index.html**

Find:
```html
  <meta name="theme-color" content="#E8E6DE" />
```
Change to:
```html
  <meta name="theme-color" content="#F7F0E6" />
```

- [ ] **Step 2: Commit all changes**

```bash
git add frontend/styles.css frontend/index.html
git commit -m "feat: apply Warm Editorial redesign — terracotta + cream mobile polish"
```

---

## Success Criteria

- 360px phone: hero title dominant, CTA full-width with 8px radius, stats visible in one row
- Feature cards: clear terracotta left stripe, text doesn't crowd border
- Dark mode: warm brown bg, no cold grey anywhere
- No horizontal scroll at any viewport width
- All other pages inherit terracotta accent automatically
