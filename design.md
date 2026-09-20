---
version: "alpha"
name: "shadcn/ui (New York)"
description: "shadcn/ui (New York) visual system, translated from the Claude Artisan catalog for use in digital products. Neutral, refined, subtle borders and rings; Small radius (0.5rem), muted zinc/slate palette"
colors:
  primary: "#18181b"
  background: "#ffffff"
  surface: "#ffffff"
  text: "#09090b"
  accent: "#2563eb"
  on-primary: "#FFFFFF"
  on-surface: "#000000"
  on-accent: "#FFFFFF"
typography:
  h1:
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif"
    fontSize: "4rem"
    fontWeight: "700"
    lineHeight: "1.05"
  body-md:
    fontFamily: "'Geist', 'Inter', system-ui, -apple-system, sans-serif"
    fontSize: "1rem"
    fontWeight: "400"
    lineHeight: "1.6"
  label-caps:
    fontFamily: "'Geist', 'Inter', system-ui, -apple-system, sans-serif"
    fontSize: "0.75rem"
    fontWeight: "600"
    letterSpacing: "0.06em"
rounded:
  sm: "0.375rem"
  md: "0.5rem"
  lg: "0.75rem"
spacing:
  sm: "8px"
  md: "16px"
  lg: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: "16px"
  button-secondary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.md}"
    padding: "16px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "24px"
  page:
    backgroundColor: "{colors.background}"
    textColor: "{colors.text}"
    padding: "16px"
---
## Overview

shadcn/ui (New York) visual system, translated from the Claude Artisan catalog for use in digital products. Neutral, refined, subtle borders and rings; Small radius (0.5rem), muted zinc/slate palette

- **Category:** flat-platform
- **Era:** 2023–present
- **Origin:** shadcn/ui (Radix + Tailwind) by shadcn; default of countless 2023+ apps.
- **Reference:** shadcn/ui showcase; Vercel/Cal.com-style apps.
- **Structural base:** shell de aplicação com navegação e cartões

**Defining traits:**
- Neutral, refined, subtle borders and rings
- Small radius (0.5rem), muted zinc/slate palette
- Accessible Radix primitives
- Understated developer-favorite polish

## Colors

- **bg** — #ffffff
- **surface** — #ffffff
- **surface-strong** — #f4f4f5
- **border** — #e4e4e7
- **text** — #09090b
- **text-muted** — #71717a
- **primary** — #18181b
- **accent** — #2563eb
- **ring** — #a1a1aa

## Typography

- Display: 'Geist', 'Inter', system-ui, sans-serif
- Body: 'Geist', 'Inter', system-ui, -apple-system, sans-serif
- Mono: 'Geist Mono', ui-monospace, 'SFMono-Regular', monospace

## Layout

- shell de aplicação com navegação e cartões
- Use a responsive grid and preserve content hierarchy.
- Collapse columns below 768px without horizontal overflow.

## Elevation & Depth

- Neutral, refined, subtle borders and rings; Small radius (0.5rem), muted zinc/slate palette; Accessible Radix primitives; Understated developer-favorite polish; sombras e elevação

## Shapes

- Radius scale: 0.375rem, 0.5rem, 0.75rem.

## Components

- Buttons keep visible focus and predictable hover/pressed states.
- Cards use the surface and radius scale from the tokens.
- Forms expose persistent labels, textual errors, and keyboard focus.

## Do's and Don'ts

- Do: follow the tokens and the structural composition.
- Do: maintain WCAG AA contrast and `prefers-reduced-motion`.
- Avoid: using the style as decoration without functional hierarchy.

<!-- Source: https://designmd.app/library/shadcn-ui · designmd.app -->
