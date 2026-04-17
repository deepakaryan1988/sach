# Design System Document: The Forensic Luminary
 
## 1. Overview & Creative North Star: "The Digital Curator"
This design system is built for the sophisticated truth-seeker. In an era of misinformation, "The Forensic Luminary" aesthetic moves away from the cluttered "dashboard" look toward a premium, editorial experience. 
 
**Creative North Star:** *The Truth in Focus.*
The interface acts as a high-end lens—clean, authoritative, and impossibly sharp. We break the traditional grid-template look through **intentional asymmetry**, where content isn't just placed, but "curated." By overlapping glassmorphic layers and using extreme typographic contrast (oversized display headers vs. precise labels), we create a futuristic environment that feels less like an app and more like a high-tech intelligence terminal.
 
---
 
### 2. Colors: Tonal Depth & Neon Precision
We leverage a deep-space palette punctuated by high-frequency neon accents. The goal is "Luminous Information"—where the color itself communicates the veracity of data.
 
*   **Background & Surface (`#0a0e14`):** A true-dark foundation that allows neon accents to "pop" without vibrating.
*   **The "No-Line" Rule:** **Strictly prohibit 1px solid borders for sectioning.** To define boundaries, use tonal shifts. For example, a `surface-container-low` section should sit directly on a `surface` background. The eye should perceive the change in depth through color value, not a stroke.
*   **Surface Hierarchy & Nesting:** Treat the UI as physical layers of obsidian and glass.
    *   **Base:** `surface`
    *   **Sectioning:** `surface-container-low`
    *   **Interactive Cards:** `surface-container-highest`
*   **The "Glass & Gradient" Rule:** Floating elements (modals, active fact-check cards) must use Glassmorphism. Combine `surface-variant` at 60% opacity with a `backdrop-filter: blur(20px)`.
*   **Signature Textures:** Apply a subtle linear gradient to Primary CTAs: `primary` (#a0ffc3) to `primary-container` (#00fc9b). This provides a "soul" to the button that flat color cannot replicate.
 
---
 
### 3. Typography: The Editorial Edge
We use a dual-typeface system to balance futuristic tech with clinical legibility.
 
*   **Display & Headlines (Space Grotesk):** This is our "Brand Voice." Use `display-lg` and `headline-md` for high-impact stats and fact-check results. It feels engineered and precise.
*   **Body & Titles (Inter):** This is our "Functional Voice." Inter provides the high legibility required for long-form debunking articles and source citations.
*   **Hierarchy as Authority:** Use extreme scale. A `display-lg` "TRUE" next to a `label-sm` timestamp creates a sophisticated, high-end editorial feel that guides the eye instantly to the conclusion.
 
---
 
### 4. Elevation & Depth: Tonal Layering
In this design system, shadows are light, and borders are ghosts.
 
*   **The Layering Principle:** Avoid shadows for static elements. Achieve depth by stacking tiers: Place a `surface-container-lowest` card on a `surface-container-low` section to create a "recessed" look.
*   **Ambient Shadows:** For floating elements only (e.g., active AI-processing chips), use a large 32px blur at 6% opacity using a tint of `on-surface` (#f1f3fc). It should feel like an ambient glow, not a drop shadow.
*   **The "Ghost Border" Fallback:** If a separator is required for accessibility, use the `outline-variant` token at **15% opacity**. This creates a "glint" on the edge of a glass card rather than a heavy line.
*   **Glassmorphism Depth:** Always use a 1px "inner glow" on glass cards using `on-surface` at 10% opacity on the top and left edges to simulate light hitting the edge of the glass.
 
---
 
### 5. Components: Futuristic Fragments
 
#### Buttons
*   **Primary:** Gradient fill (`primary` to `primary-container`). Roundedness: `md` (0.375rem). No border. Text color: `on-primary`.
*   **Secondary:** Glass-fill. `surface-variant` at 40% opacity with a `backdrop-blur`. 
*   **Tertiary:** Ghost style. No background, `primary` text, high-letter spacing for a "tech" feel.
 
#### Fact-Check "Truth" Cards
*   **Forbid dividers.** Use `surface-container-highest` for the card body and `surface-container-low` for the "Source Credits" footer of the card to create separation through value.
*   **Status Accents:** A 4px vertical "Neon Stripe" on the left edge using `primary` (True), `error` (False), or `tertiary` (Uncertain).
 
#### Input Fields
*   **Base State:** `surface-container-highest` background, no border, `sm` roundedness. 
*   **Active/Focus State:** A "Ghost Border" (20% opacity `primary`) and a subtle outer glow of the same color.
 
#### AI-Pulse Progress Bar
*   A slim, 2px height bar. Background: `surface-variant`. Fill: A moving gradient from `secondary` (#ac89ff) to `primary` (#a0ffc3) to represent the AI "thinking."
 
---
 
### 6. Do's and Don'ts
 
#### Do:
*   **Use Asymmetry:** Place the main fact-check result off-center to create a dynamic, modern layout.
*   **Embrace Negative Space:** Allow at least 24px–32px of breathing room between major sections.
*   **Use Neon Sparingly:** Use neon colors only for status and intent. Overusing them will break the "Premium" feel and move into "Gaming" territory.
 
#### Don't:
*   **No 100% Opaque Borders:** Never use a solid, high-contrast line to separate content.
*   **No Standard Shadows:** Avoid the "Material Design" style heavy shadows. We are building for light and transparency, not weight.
*   **No Center-Aligning Long Text:** Keep editorial content left-aligned for maximum readability and a professional "Report" aesthetic.
*   **No Pure Grey:** Use our tinted neutrals (`surface-variant`) to ensure the dark mode feels "deep sea" rather than "dead grey."