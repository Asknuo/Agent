/**
 * Internationalization (i18n) core module.
 *
 * Provides locale types, translation resource structure,
 * and the translate function with parameter interpolation support.
 */

export type Locale = 'zh-CN' | 'en-US';

/**
 * Translation resource: a mapping from locale to a flat key-value dictionary.
 */
export type TranslationResource = Record<Locale, Record<string, string>>;

/**
 * Translates a key into the target locale's text.
 *
 * - If the locale or key is not found, returns the key itself (graceful degradation).
 * - Supports parameter interpolation: `{paramName}` placeholders are replaced
 *   with corresponding values from the `params` object.
 *
 * @param key - The translation key (e.g. 'login.title')
 * @param locale - The target locale
 * @param resources - The full translation resource map
 * @param params - Optional interpolation parameters
 * @returns The translated (and interpolated) string, or the key itself on miss
 */
export function translate(
  key: string,
  locale: Locale,
  resources: TranslationResource,
  params?: Record<string, string | number>,
): string {
  const localeResources = resources[locale];
  if (!localeResources) return key;

  let text = localeResources[key];
  if (text === undefined) return key;

  // Parameter interpolation
  if (params) {
    for (const [paramKey, paramValue] of Object.entries(params)) {
      // Use split/join to avoid special replacement patterns ($&, $$, etc.)
      text = text.split(`{${paramKey}}`).join(String(paramValue));
    }
  }

  return text;
}
