/**
 * Property-Based Tests for the i18n translate function.
 *
 * Validates:
 * - Correctness Property 12: Unregistered keys return the key itself
 * - Correctness Property 13: Parameter interpolation completeness
 * - Translation resource completeness (all keys present in all locales)
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { translate, Locale, TranslationResource } from '../i18n';
import zhCN from '../locales/zh-CN';
import enUS from '../locales/en-US';

// ── Build the full resource for testing ──

const resources: TranslationResource = {
  'zh-CN': zhCN,
  'en-US': enUS,
};

const ALL_LOCALES: Locale[] = ['zh-CN', 'en-US'];

// ── Arbitraries ──

const localeArb: fc.Arbitrary<Locale> = fc.constantFrom(...ALL_LOCALES);

// Generate keys that are guaranteed NOT to exist in our resources
const unregisteredKeyArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter(k => !zhCN[k] && !enUS[k]);

// Pick a random registered key from the resource
const registeredKeyArb: fc.Arbitrary<string> = fc.constantFrom(...Object.keys(zhCN));

// ── Property Tests ──

describe('Property 12: Translation key fallback (unregistered key returns key itself)', () => {
  it('any unregistered key returns the key itself for any locale', () => {
    fc.assert(
      fc.property(unregisteredKeyArb, localeArb, (key, locale) => {
        const result = translate(key, locale, resources);
        expect(result).toBe(key);
      }),
      { numRuns: 200 },
    );
  });

  it('empty string key returns empty string (edge case)', () => {
    for (const locale of ALL_LOCALES) {
      // Empty string is not a registered key, so it should return itself
      const result = translate('', locale, resources);
      expect(result).toBe('');
    }
  });
});

describe('Property 13: Parameter interpolation completeness', () => {
  it('all {paramName} placeholders are replaced when params are provided', () => {
    // Extract keys that contain placeholders
    const keysWithParams = Object.entries(zhCN)
      .filter(([, v]) => /\{[^}]+\}/.test(v))
      .map(([k]) => k);

    fc.assert(
      fc.property(
        fc.constantFrom(...keysWithParams),
        localeArb,
        (key, locale) => {
          const text = resources[locale][key];
          // Extract all param names from the template
          const paramNames = [...text.matchAll(/\{([^}]+)\}/g)].map(m => m[1]);

          // Build params object with arbitrary values
          const params: Record<string, string> = {};
          for (const name of paramNames) {
            params[name] = `value_${name}`;
          }

          const result = translate(key, locale, resources, params);

          // After interpolation, no {paramName} placeholders should remain
          for (const name of paramNames) {
            expect(result).not.toContain(`{${name}}`);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('params with random string values are correctly interpolated', () => {
    fc.assert(
      fc.property(
        localeArb,
        fc.string({ minLength: 1, maxLength: 20 }),
        (locale, value) => {
          // Use a known key with a param: 'chat.welcome.title' has {username}
          const result = translate('chat.welcome.title', locale, resources, { username: value });
          expect(result).toContain(value);
          expect(result).not.toContain('{username}');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('numeric params are converted to string and interpolated', () => {
    fc.assert(
      fc.property(
        localeArb,
        fc.integer({ min: 0, max: 10000 }),
        (locale, count) => {
          // 'metrics.raw.more' has {count}
          const result = translate('metrics.raw.more', locale, resources, { count });
          expect(result).toContain(String(count));
          expect(result).not.toContain('{count}');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('translate without params leaves placeholders intact', () => {
    fc.assert(
      fc.property(localeArb, (locale) => {
        const result = translate('chat.welcome.title', locale, resources);
        expect(result).toContain('{username}');
      }),
      { numRuns: 10 },
    );
  });
});

describe('Translation resource completeness', () => {
  it('every key in zh-CN exists in en-US', () => {
    const zhKeys = Object.keys(zhCN);
    for (const key of zhKeys) {
      expect(enUS).toHaveProperty(key);
    }
  });

  it('every key in en-US exists in zh-CN', () => {
    const enKeys = Object.keys(enUS);
    for (const key of enKeys) {
      expect(zhCN).toHaveProperty(key);
    }
  });

  it('both locales have the exact same set of keys', () => {
    const zhKeys = Object.keys(zhCN).sort();
    const enKeys = Object.keys(enUS).sort();
    expect(zhKeys).toEqual(enKeys);
  });

  it('no translation value is empty string', () => {
    for (const locale of ALL_LOCALES) {
      for (const [key, value] of Object.entries(resources[locale])) {
        expect(value.length, `Key "${key}" in ${locale} is empty`).toBeGreaterThan(0);
      }
    }
  });

  it('parameterized keys have matching placeholders across all locales', () => {
    const allKeys = Object.keys(zhCN);
    for (const key of allKeys) {
      const zhParams = [...(zhCN[key].matchAll(/\{([^}]+)\}/g))].map(m => m[1]).sort();
      const enParams = [...(enUS[key].matchAll(/\{([^}]+)\}/g))].map(m => m[1]).sort();
      expect(zhParams, `Param mismatch for key "${key}"`).toEqual(enParams);
    }
  });
});
