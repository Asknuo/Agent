/**
 * Theme configuration module for Dark Mode support.
 *
 * Provides theme mode types, CSS variable mappings for light/dark themes,
 * and utility functions for toggling, resolving, and applying themes.
 */

export type ThemeMode = 'light' | 'dark' | 'system';

export interface ThemeConfig {
  cssVariables: {
    '--bg-primary': string;
    '--bg-secondary': string;
    '--text-primary': string;
    '--text-secondary': string;
    '--border-color': string;
    '--accent-color': string;
    '--msg-user-bg': string;
    '--msg-bot-bg': string;
    '--input-bg': string;
    '--shadow-color': string;
  };
}

export const THEME_CONFIGS: Record<'light' | 'dark', ThemeConfig> = {
  light: {
    cssVariables: {
      '--bg-primary': '#ffffff',
      '--bg-secondary': '#f4f5f7',
      '--text-primary': '#1f2937',
      '--text-secondary': '#9ca3af',
      '--border-color': '#f0f0f0',
      '--accent-color': '#6366f1',
      '--msg-user-bg': 'linear-gradient(135deg, #6366f1, #818cf8)',
      '--msg-bot-bg': '#f5f5f5',
      '--input-bg': '#f9fafb',
      '--shadow-color': 'rgba(0, 0, 0, 0.06)',
    },
  },
  dark: {
    cssVariables: {
      '--bg-primary': '#1a1b1e',
      '--bg-secondary': '#111214',
      '--text-primary': '#e5e7eb',
      '--text-secondary': '#9ca3af',
      '--border-color': '#2d2f34',
      '--accent-color': '#818cf8',
      '--msg-user-bg': 'linear-gradient(135deg, #4f46e5, #6366f1)',
      '--msg-bot-bg': '#2d2f34',
      '--input-bg': '#23252a',
      '--shadow-color': 'rgba(0, 0, 0, 0.3)',
    },
  },
};

const THEME_CYCLE: ThemeMode[] = ['light', 'dark', 'system'];

/**
 * Cycles theme mode: light → dark → system → light
 */
export function toggleTheme(current: ThemeMode): ThemeMode {
  const idx = THEME_CYCLE.indexOf(current);
  return THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
}

/**
 * Resolves a ThemeMode to an actual 'light' or 'dark' value.
 * When mode is 'system', uses the OS preference via matchMedia.
 */
export function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'light';
  }
  return mode;
}

/**
 * Applies the resolved theme to the document root element by setting
 * the data-theme attribute and updating all CSS variables.
 */
export function applyTheme(resolved: 'light' | 'dark'): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', resolved);
  const vars = THEME_CONFIGS[resolved].cssVariables;
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value);
  }
}
