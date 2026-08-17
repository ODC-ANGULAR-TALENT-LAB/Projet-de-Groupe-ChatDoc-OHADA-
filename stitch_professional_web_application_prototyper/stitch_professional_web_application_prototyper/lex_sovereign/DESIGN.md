---
name: Lex-Sovereign
colors:
  surface: '#fbf9f3'
  surface-dim: '#dcdad4'
  surface-bright: '#fbf9f3'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3ed'
  surface-container: '#f0eee8'
  surface-container-high: '#eae8e2'
  surface-container-highest: '#e4e2dd'
  on-surface: '#1b1c18'
  on-surface-variant: '#45464e'
  inverse-surface: '#30312d'
  inverse-on-surface: '#f3f1eb'
  outline: '#75777f'
  outline-variant: '#c5c6cf'
  surface-tint: '#4f5e81'
  primary: '#041534'
  on-primary: '#ffffff'
  primary-container: '#1b2a4a'
  on-primary-container: '#8392b7'
  inverse-primary: '#b7c6ee'
  secondary: '#755b00'
  on-secondary: '#ffffff'
  secondary-container: '#fed255'
  on-secondary-container: '#735a00'
  tertiary: '#001b0b'
  on-tertiary: '#ffffff'
  tertiary-container: '#00321a'
  on-tertiary-container: '#51a170'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d9e2ff'
  primary-fixed-dim: '#b7c6ee'
  on-primary-fixed: '#0a1a3a'
  on-primary-fixed-variant: '#384668'
  secondary-fixed: '#ffe08e'
  secondary-fixed-dim: '#ecc246'
  on-secondary-fixed: '#241a00'
  on-secondary-fixed-variant: '#584400'
  tertiary-fixed: '#a1f5bc'
  tertiary-fixed-dim: '#86d8a2'
  on-tertiary-fixed: '#00210f'
  on-tertiary-fixed-variant: '#00522d'
  background: '#fbf9f3'
  on-background: '#1b1c18'
  surface-variant: '#e4e2dd'
  surface-paper: '#F4F2EC'
  surface-white: '#FFFFFF'
  legal-navy: '#1B2A4A'
  citation-gold: '#C9A227'
  validation-green: '#2A7D4F'
  border-muted: '#D1CEC4'
typography:
  display-lg:
    fontFamily: Source Serif 4
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Source Serif 4
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  legal-article:
    fontFamily: Source Serif 4
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  ui-body:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  ui-medium:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '500'
    lineHeight: 24px
  ui-label:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  metadata:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  legal-article-mobile:
    fontFamily: Source Serif 4
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base-unit: 4px
  container-padding: 24px
  gutter: 16px
  sidebar-width: 280px
  max-content-width: 800px
---

## Brand & Style

The design system is engineered to evoke **authority, certainty, and legal rigor**. Targeting legal professionals, tax consultants, and corporate jurists in the OHADA zone, the UI moves away from "playful AI" tropes in favor of a "Digital Law Library" persona. 

The aesthetic is **Institutional Minimalism**: a blend of high-end legal publishing and modern functionalism. It prioritizes long-form legibility and structural hierarchy to instill confidence. The interface feels like a premium professional tool—sober, stable, and meticulously organized—where the AI is an expert assistant rather than a creative companion.

**Key Stylistic Pillars:**
- **Paper-First Backgrounds:** Using off-white/cream tones to reduce eye strain and mimic physical legal documents.
- **Typographic Authority:** Clear distinction between "Interface" (Sans) and "The Law" (Serif).
- **Sobriety:** Minimal use of shadows, relying instead on clean borders and tonal layering to define space.
- **Verifiability:** Design patterns that emphasize the "Source" (legal basis) above all else.

## Colors

The palette is rooted in traditional legal aesthetics. **Midnight Blue** provides the institutional weight, used for headers and primary navigation to signal stability. **Citation Gold** is reserved strictly for high-value legal references, highlights, and primary actions, acting as a "gilded edge" for official content.

**Forest Green** is utilized sparingly for success states and validated legal paths. The background strategy uses **Off-White (#F4F2EC)** as the canvas to simulate premium paper, with pure **White (#FFFFFF)** cards sitting atop it to create a subtle, natural elevation without relying on heavy digital shadows.

## Typography

This system uses a disciplined pairing to create psychological separation between the application and the law. 

1.  **Source Serif 4 (The Voice of Law):** Used for all legal content, article text, and section headers. This serif font echoes official gazettes and law books, providing the necessary gravitas for citations.
2.  **Inter (The Voice of the Interface):** Used for AI-generated responses, navigation, buttons, and system feedback. It provides a clean, neutral contrast that ensures high utility and speed of reading.

**Scale Strategy:** Legal text maintains a generous line height (1.5x - 1.6x) to facilitate the reading of complex articles. On mobile, serif sizes are slightly reduced but line heights remain open to ensure accessibility during field research.

## Layout & Spacing

The layout philosophy follows a **Fixed-Fluid Hybrid** model. Navigation is anchored by a persistent sidebar (on desktop) for quick access to the Library and Calculators. The main content area is capped at `800px` to maintain optimal line lengths for reading legal articles.

**Layout Grid:**
- **Desktop:** 12-column grid with a fixed `280px` sidebar. Content is centered in the remaining viewport.
- **Tablet:** 8-column grid; sidebar collapses into a drawer.
- **Mobile:** Single column with `16px` horizontal margins.

**Rhythm:** We use a 4px base unit. Generous whitespace is used between "Legal Basis" blocks to allow the user to mentally process distinct citations.

## Elevation & Depth

To maintain a "sober" professional atmosphere, the system avoids heavy drop shadows and modern "floating" effects.

1.  **Tonal Layering:** The primary depth indicator is color. The `#F4F2EC` background acts as the floor, while `#FFFFFF` surfaces (cards/chat bubbles) indicate active content.
2.  **Low-Contrast Outlines:** Instead of shadows, UI elements use a `1px` solid border in `#D1CEC4` (Border Muted).
3.  **Active States:** When a legal block is expanded, it uses a subtle 2px vertical accent of `Citation Gold` on the left border rather than an elevation lift.
4.  **Sober Shadows:** Only the global Sidebar and Modals use a very soft, high-diffusion shadow (`0 4px 20px rgba(27, 42, 74, 0.08)`) to separate them from the reading plane.

## Shapes

The shape language is **Soft (0.25rem)**. We avoid completely sharp corners to keep the tool approachable, but we also avoid high roundedness (pills) to maintain a serious, structured look.

- **Buttons & Inputs:** 4px radius.
- **Legal Citations & Cards:** 8px radius for a slightly softer container feel.
- **Chat Bubbles:** 8px radius, except for the "pointing" corner which remains sharp to denote the speaker.

## Components

### Bloc Base Légale (Legal Basis Block)
The signature component. It is a white card with a `1px` border. It features a `4px` left-border accent in **Citation Gold**. The header uses **Inter Bold** for the article number and **Source Serif** for the article title. The content is collapsible to manage long texts.

### Chat Bubbles
- **User:** Right-aligned, Midnight Blue background with White Inter text. Sharp bottom-right corner.
- **Assistant:** Left-aligned, White background with Midnight Blue border. Inter text for the AI's commentary. Legal citations within the bubble appear as nested **Blocs Base Légale**.

### Sidebar Navigation
Dark theme implementation using **Midnight Blue (#1B2A4A)**. Links use **Inter Medium** with Gold icons when active. It houses the "Library," "Calculators," and "History."

### Buttons
- **Primary:** Midnight Blue background, White text.
- **Secondary/Citation:** Gold border, Gold text, no background.
- **Ghost:** No border/background, used for "See original PDF" links.

### Inputs
Search bars and chat inputs are white with a muted border and a **Citation Gold** focus ring. They use **Inter** for placeholder and input text to emphasize the "utility" of the action.