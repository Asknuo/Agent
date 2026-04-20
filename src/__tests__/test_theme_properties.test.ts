/**
 * Property-Based Tests for Theme System
 *
 * Properties tested:
 * 1. toggleTheme cycle: from any starting ThemeMode, 3 consecutive toggles return to the original value
 * 2. resolveTheme determinism: for any ThemeMode, resolveTheme returns only 'light' or 'dark'
 * 3. THEME_CONFIGS completeness: both light and dark configs have all required CSS variables
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { toggleTheme, resolveTheme, THEME_CONFIGS, type ThemeMode } from '../theme';

// ── Arbitraries ──

const themeModeArb: fc.Arbitrary<ThemeMode> = fc.constantFrom('light', 'dark', 'system');

// ── Property Tests ──

describe('Theme system properties', () => {
  describe('toggleTheme cycle property', () => {
    it('3 consecutive toggles return to the original value for any starting ThemeMode', () => {
      fc.assert(
        fc.property(themeModeArb, (startMode) => {
          const after1 = toggleTheme(startMode);
          const after2 = toggleTheme(after1);
          const after3 = toggleTheme(after2);

          expect(after3).toBe(startMode);
        }),
        { numRuns: 100 },
      );
    });

    it('each toggle produces a different value than the input', () => {
      fc.assert(
        fc.property(themeModeArb, (mode) => {
          const next = toggleTheme(mode);
          expect(next).not.toBe(mode);
        }),
        { numRuns: 100 },
      );
    });

    it('toggle always returns a valid ThemeMode', () => {
      const validModes: ThemeMode[] = ['light', 'dark', 'system'];
      fc.assert(
        fc.property(themeModeArb, (mode) => {
          const result = toggleTheme(mode);
          expect(validModes).toContain(result);
        }),
        { numRuns: 100 },
      );
    });
  });

  describe('resolveTheme determinism property', () => {
    it('resolveTheme always returns only "light" or "dark" for any ThemeMode', () => {
      fc.assert(
        fc.property(themeModeArb, (mode) => {
          const resolved = resolveTheme(mode);
          expect(['light', 'dark']).toContain(resolved);
        }),
        { numRuns: 100 },
      );
    });

    it('resolveTheme("light") always returns "light"', () => {
      expect(resolveTheme('light')).toBe('light');
    });

    it('resolveTheme("dark") always returns "dark"', () => {
      expect(resolveTheme('dark')).toBe('dark');
    });

    it('resolveTheme("system") returns either "light" or "dark"', () => {
      const result = resolveTheme('system');
      expect(['light', 'dark']).toContain(result);
    });
  });

  describe('THEME_CONFIGS completeness', () => {
    const requiredVars = [
      '--bg-primary',
      '--bg-secondary',
      '--text-primary',
      '--text-secondary',
      '--border-color',
      '--accent-color',
      '--msg-user-bg',
      '--msg-bot-bg',
      '--input-bg',
      '--shadow-color',
    ] as const;

    it('both light and dark configs contain all required CSS variables', () => {
      for (const theme of ['light', 'dark'] as const) {
        const vars = THEME_CONFIGS[theme].cssVariables;
        for (const varName of requiredVars) {
          expect(vars).toHaveProperty(varName);
          expect(vars[varName]).toBeTruthy();
        }
      }
    });

    it('light and dark configs have the same set of CSS variable keys', () => {
      const lightKeys = Object.keys(THEME_CONFIGS.light.cssVariables).sort();
      const darkKeys = Object.keys(THEME_CONFIGS.dark.cssVariables).sort();
      expect(lightKeys).toEqual(darkKeys);
    });
  });
});
