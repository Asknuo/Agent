import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { Locale, TranslationResource, translate } from './i18n';
import zhCN from './locales/zh-CN';
import enUS from './locales/en-US';
import antdZhCN from 'antd/locale/zh_CN';
import antdEnUS from 'antd/locale/en_US';

const STORAGE_KEY = 'xiaozhi_locale';

const resources: TranslationResource = {
  'zh-CN': zhCN,
  'en-US': enUS,
};

const antdLocaleMap = {
  'zh-CN': antdZhCN,
  'en-US': antdEnUS,
} as const;

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  antdLocale: typeof antdZhCN | typeof antdEnUS;
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

function readStoredLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'zh-CN' || stored === 'en-US') {
      return stored;
    }
  } catch {
    // localStorage unavailable
  }
  return 'zh-CN';
}

function persistLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // localStorage unavailable — silently ignore
  }
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    persistLocale(newLocale);
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => translate(key, locale, resources, params),
    [locale],
  );

  const antdLocale = antdLocaleMap[locale];

  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, t, antdLocale }),
    [locale, setLocale, t, antdLocale],
  );

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return ctx;
}
