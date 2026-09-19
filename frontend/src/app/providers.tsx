import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';

import { AppContext } from './appContext';
import type { ThemePreference, LanguagePreference } from './appContext';

/**
 * Application-wide providers.
 *
 * Currently routing plus a tiny context for the active asset. This is the seam where an auth
 * provider, a query client and a theme provider will be added.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [activeUrn, setActiveUrn] = useState<string | null>(null);
  const [theme, setTheme] = useState<ThemePreference>(() => {
    if (typeof window === 'undefined') return 'dark';
    const saved = window.localStorage.getItem('metamind-theme');
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved;
    return 'dark';
  });
  const [language, setLanguage] = useState<LanguagePreference>(() => {
    if (typeof window === 'undefined') return 'English';
    const saved = window.localStorage.getItem('metamind-language');
    if (saved === 'English' || saved === 'Spanish' || saved === 'German') return saved;
    return 'English';
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('metamind-theme', theme);
    const root = document.documentElement;
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const resolved = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;
    root.setAttribute('data-theme', resolved);
  }, [theme]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('metamind-language', language);
    document.documentElement.lang = language.toLowerCase();
  }, [language]);

  const value = useMemo(
    () => ({ activeUrn, setActiveUrn, theme, setTheme, language, setLanguage }),
    [activeUrn, theme, language],
  );

  return (
    <BrowserRouter>
      <AppContext.Provider value={value}>{children}</AppContext.Provider>
    </BrowserRouter>
  );
}
