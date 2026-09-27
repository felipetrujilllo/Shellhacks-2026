// Reads palette tokens from theme.css for code that can't use CSS var() — MapLibre paint
// properties and inline swatch styles.

/**
 * The value of CSS custom property `name` on the document root (theme.css's `:root`), trimmed,
 * or `fallback` when the token is unset (e.g. in unit tests, where theme.css isn't loaded).
 * Pass today's color from theme.css as `fallback`; theme.test.ts checks every call site agrees.
 *
 * The map's color constants call this once, when their module loads. main.tsx imports theme.css
 * before App, so the tokens are applied by then; after editing a map token, reload the page.
 */
export function themeColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}
