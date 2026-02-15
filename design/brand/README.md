# Saaf Baat — Brand Assets

This folder holds **product-safe** brand assets for Saaf Baat (icon + lockups) and usage rules for frontend work.

## Core mark (icon)

**Meaning:** a calm **dot** (focus) + a small **clarity spark** (trust / “saaf”) — simple enough to read at 16–24px.

**Primary color:** Teal `#52B7A3`

### Files
- Icon (color): `design/brand/icon/saaf-baat-icon.svg`
- Icon (mono, uses `currentColor`): `design/brand/icon/saaf-baat-icon-mono.svg`
- Icon (white): `design/brand/icon/saaf-baat-icon-white.svg`

### PNG references (from AI mockup crops)
These are **reference bitmaps** (not perfect/flat; may include subtle AI shading). Prefer the SVGs for web UI.
- `design/brand/png/icon-light-512.png`
- `design/brand/png/icon-dark-512.png`

## Lockups (PNG references)
Until we recreate the wordmark as vector (font + spacing), these are reference crops for direction:
- `design/brand/png/lockup-horizontal-light.png`
- `design/brand/png/lockup-horizontal-dark.png`
- `design/brand/png/lockup-stacked-light.png`
- `design/brand/png/lockup-stacked-dark.png`

## Usage rules

### Clear space
Keep at least **0.5× the dot diameter** of clear space on all sides of the icon.

### Minimum sizes
- **Icon:** 16px minimum (24px recommended for headers)
- **Header brand:** 18–20px icon + 16–18px wordmark text (web)

### Web component sizing spec
When using `frontend/src/components/Logo.tsx`:
- Header desktop: `size={26}` with **10px** icon-to-wordmark gap
- Header mobile: `size={22}` and keep mark top-aligned with first line of greeting
- Compact controls (chips/buttons): avoid using the logo below `size={18}`

### Backgrounds
- Light surfaces (paper): teal icon + ink text
- Dark surfaces: teal icon + white text

### Don’t
- Don’t add outlines, heavy shadows, gradients, or extra details to the icon.
- Don’t rotate, stretch, or change the ray count/geometry.
