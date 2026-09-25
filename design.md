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

---

## 平台补充规范:新增/邀请类主按钮(2026-09-25 起,后续页面一律遵循)

- **页头右上(acts 区)的「新建/邀请/添加/绑定」类主按钮,必须带 `+` 图标**:
  - ui/Button 写法:`<Button variant="primary" onClick={...}><Plus className="w-4 h-4 mr-1" />新建××</Button>`
  - 原生类写法:`<button className="btn btn-pri" onClick={...}><Plus className="w-4 h-4 mr-1" />邀请新用户</button>`
  - 图标统一 lucide-react `Plus`,`w-4 h-4 mr-1`,文案在前图标在后不换序
- **不加 Plus 的例外**:表单提交按钮(创建中…/保存)、从对象派生的语义化创建(如需求页「创建开发任务」用 FileText)、行内小按钮
- 参照实现:`admin/SkillsMarket.tsx:119`、`admin/UserManagementPage.tsx`(邀请新用户)、`knowledge/KnowledgeBase.tsx`(新建条目)、`manage/DimensionPage.tsx:125`
