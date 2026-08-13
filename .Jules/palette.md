## 2024-05-15 - [Add aria-labels to icon-only buttons & keyboard focus styling]
**Learning:** [Accessibility insight]
Added `aria-label`s to multiple icon-only buttons across the UI for screen reader friendliness, added `role="button"` and `tabindex="0"` to the `.close-btn` span to make it focusable, and added `:focus-visible` to all `.btn`, `.close-btn`, and `.tour-close-btn` classes to provide visual cues for keyboard navigation while avoiding default outlines for mouse clicks.
**Action:** Always ensure that icon-only interactive elements contain `aria-label`s and that clickable spans have `role="button"` and `tabindex="0"`. Additionally, explicitly add `:focus-visible` styling (like `outline`) when `outline: none;` is used.
