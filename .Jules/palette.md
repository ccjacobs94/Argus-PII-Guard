## 2024-05-15 - [Add aria-labels to icon-only buttons & keyboard focus styling]
**Learning:** [Accessibility insight]
Added `aria-label`s to multiple icon-only buttons across the UI for screen reader friendliness, added `role="button"` and `tabindex="0"` to the `.close-btn` span to make it focusable, and added `:focus-visible` to all `.btn`, `.close-btn`, and `.tour-close-btn` classes to provide visual cues for keyboard navigation while avoiding default outlines for mouse clicks.
**Action:** Always ensure that icon-only interactive elements contain `aria-label`s and that clickable spans have `role="button"` and `tabindex="0"`. Additionally, explicitly add `:focus-visible` styling (like `outline`) when `outline: none;` is used.

## 2025-02-13 - Missing ARIA labels in dynamic JS buttons
**Learning:** This app frequently renders icon-only buttons via JS template literals (e.g., .delete-folder-btn, .delete-exception-btn) which lacked the aria-labels that were present on statically defined buttons in index.html. Screen readers could not announce these buttons correctly.
**Action:** Always check dynamically generated HTML templates in script.js for icon-only buttons to ensure they also receive appropriate aria-labels.
