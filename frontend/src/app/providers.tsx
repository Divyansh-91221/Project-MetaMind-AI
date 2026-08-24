import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';

import { AppContext } from './appContext';
import type { ThemePreference } from './appContext';

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

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('metamind-theme', theme);
    const root = document.documentElement;
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const resolved = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;
    root.setAttribute('data-theme', resolved);
  }, [theme]);

  const value = useMemo(
    () => ({ activeUrn, setActiveUrn, theme, setTheme }),
    [activeUrn, theme],
  );

  return (
    <BrowserRouter>
      <AppContext.Provider value={value}>{children}</AppContext.Provider>
    </BrowserRouter>
  );
}
