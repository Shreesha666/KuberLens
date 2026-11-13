# TASK: Adopt CoolAdmin Typography and Text Styling Only

## 1. Reference URLs

Use the following CoolAdmin pages as visual references:

**Dashboard:**
https://preview.colorlib.com/theme/cooladmin/index.html

**Typography:**
https://preview.colorlib.com/theme/cooladmin/typo.html

The typography page (`typo.html`) is the primary reference for this task.

## 2. Objective

I want to adopt ONLY the typography system and text styling of the CoolAdmin template in my existing Indian Stock Market Research & Intelligence Platform.

The goal is to achieve a clean, elegant, professional financial application with typography inspired by CoolAdmin.

**This is NOT a template migration or UI redesign.**

Do not copy the CoolAdmin layout, dashboard structure, navigation, cards, widgets or components.

## 3. Strict Scope: What to Adopt

Study the CoolAdmin typography reference and selectively adopt the following:

### A. Font Family
- Identify the font family used by CoolAdmin.
- Use Inter variable font if confirmed by the current reference implementation.
- Define suitable fallback fonts.
- Maintain consistent font rendering throughout the application.

### B. Typography Hierarchy
Adopt a consistent hierarchy for:

- H1 – Main page titles.
- H2 – Major section headings.
- H3 – Subsection headings.
- H4–H6 – Smaller section and component headings.
- Body text.
- Small descriptions.
- Captions.
- Helper text.

### C. Font Properties
Study and implement appropriate values for:

- Font size.
- Font weight.
- Line height.
- Letter spacing.
- Text transformation.
- Text alignment.

### D. Text Colours
Define consistent styles for:

- Primary text.
- Secondary text.
- Muted text.
- Disabled text.
- Link text.
- Heading text.
- Positive financial values.
- Negative financial values.
- Warning and informational text.

Preserve the application's existing semantic colour conventions.

### E. Additional Text Styling
Adopt suitable styling for:

- Paragraphs.
- Inline text emphasis.
- Bold and italic text.
- Lists and nested lists.
- Blockquotes.
- Links and hover states.
- Form labels.
- Input placeholders.
- Table headings and cells.
- Breadcrumbs.
- Badges and status labels.
- Tooltips and helper messages.

## 4. Existing Architecture – Must Remain Unchanged

Preserve the existing project architecture and implementation.

The following must NOT be replaced or redesigned:

- Django modular monolith.
- Existing Django applications.
- Existing URL structure.
- Existing authentication and permission system.
- Existing common application shell.
- Existing sidebar and header.
- Existing Tabler-based UI components and layout.
- Bootstrap 5.
- HTMX navigation and partial rendering.
- Browser back/forward navigation.
- Existing responsive behaviour.
- TradingView Lightweight Charts.
- Apache ECharts.
- Existing business logic and APIs.
- Existing database models and data.

## 5. Centralised Typography Design System

Create or update a central typography stylesheet.

Use CSS custom properties for consistent styling.

Example structure:

```css
:root {
    --font-family-base: "Inter", sans-serif;

    --font-size-base: 0.875rem;
    --font-size-small: 0.75rem;
    --font-size-large: 1rem;

    --font-weight-normal: 400;
    --font-weight-medium: 500;
    --font-weight-semibold: 600;
    --font-weight-bold: 700;

    --line-height-base: 1.5;

    --text-primary: #212529;
    --text-secondary: #6c757d;
    --text-muted: #8a94a6;
}
```

These are initial examples only. Inspect the actual CoolAdmin reference and existing project before finalising the values.

Avoid unnecessary global CSS overrides.

The typography system must be reusable across all Django applications.

## 6. Apply Typography Consistently

Apply the new typography system to existing pages and reusable components, including:

- Main dashboard.
- Market overview.
- Stock research.
- Stock detail pages.
- Technical analysis.
- Fundamental analysis.
- Portfolio.
- Holdings.
- Transactions.
- Watchlists.
- Screeners.
- Swing trading.
- IPO Intelligence Centre.
- News and events.
- Alerts and notifications.
- Settings.
- Forms and tables.

Do not change page layouts or component structures to achieve this.

## 7. Special Attention: Financial Data

This is a financial research platform, so readability of numbers is particularly important.

Ensure consistent typography for:

- Stock prices.
- Percentage changes.
- Portfolio values.
- Profit and loss.
- Returns.
- Quantity.
- Average purchase price.
- Market capitalisation.
- Financial ratios.
- Revenue and profit figures.
- Entry prices.
- Stop-loss levels.
- Target prices.
- Subscription figures.
- IPO price bands.

Use tabular numerals where appropriate:

```css
.financial-value {
    font-variant-numeric: tabular-nums;
}
```

Maintain proper alignment of numerical columns in tables.

Do not change any financial calculations or data presentation logic.

## 8. Chart Compatibility

Do not modify the charting architecture.

Preserve:

- TradingView Lightweight Charts for stock price and technical charts.
- Apache ECharts for dashboards and analytical visualisations.

Ensure that typography changes do not break:

- Chart labels.
- Axis labels.
- Tooltips.
- Legends.
- Crosshair information.
- Chart container dimensions.
- Chart rendering after HTMX navigation.

Only adjust chart typography if necessary and compatible with the existing implementation.

## 9. Responsive and Theme Compatibility

Ensure that typography remains readable across:

- Desktop.
- Laptop.
- Tablet.
- Mobile.

Preserve existing light and dark theme functionality, if implemented.

Text colours must maintain sufficient contrast in both themes.

Avoid excessively large headings or oversized text that wastes space in a financial dashboard.

## 10. Implementation Workflow

### Step 1 – Inspect
Before making changes:

- Inspect the existing CSS architecture.
- Identify global stylesheets.
- Identify Bootstrap and Tabler overrides.
- Inspect shared Django templates.
- Inspect existing design tokens.
- Review the CoolAdmin dashboard and `typo.html` typography reference.

### Step 2 – Prepare
Document:

- Current typography implementation.
- Proposed font family.
- Proposed typography scale.
- Text colour palette.
- Files that need modification.

### Step 3 – Implement
- Create or update the central typography stylesheet.
- Introduce reusable typography variables.
- Apply styles to shared templates and components.
- Remove conflicting typography rules only when safe.
- Avoid unnecessary changes to individual applications.

### Step 4 – Validate
Test:

- Dashboard.
- Stock detail page.
- Portfolio and holdings.
- IPO pages.
- Tables and forms.
- HTMX navigation.
- Browser history.
- Chart rendering.
- Responsive layouts.
- Light and dark themes, if supported.

### Step 5 – Document
Update the project documentation with:

- Adopted font family.
- Typography scale.
- Font weights.
- Text colour variables.
- Central stylesheet location.
- Reusable CSS classes.
- Modified files.
- Validation results.

## 11. Acceptance Criteria

The implementation is complete only when:

1. The application uses a consistent CoolAdmin-inspired typography system.
2. The correct CoolAdmin `typo.html` reference has been used.
3. Text styling is consistent across all existing modules.
4. Financial numbers remain highly readable.
5. The existing application layout remains unchanged.
6. Existing sidebar and header remain unchanged.
7. No existing functionality is broken.
8. Charts continue rendering correctly.
9. HTMX navigation and browser history work correctly.
10. No unnecessary dependencies are introduced.
11. The implementation is centralised and maintainable.

## 12. Strict Final Instruction

**Change typography and text styling ONLY.**

Do not redesign the dashboard.

Do not migrate to the CoolAdmin template.

Do not replace Tabler or Bootstrap.

Do not change existing layouts, navigation, cards, widgets, charts, routes, APIs, models or business logic.

First inspect the existing project, then implement the typography changes in a controlled and reusable manner.

After completion, provide a summary of modified files, screenshots of before and after, validation results and any remaining issues.****