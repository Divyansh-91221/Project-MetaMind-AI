import { createContext, useContext } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';
export type LanguagePreference = 'English' | 'Spanish' | 'German';

export interface AppContextValue {
  /** The asset the user is currently looking at. Passed to the Copilot as page context. */
  activeUrn: string | null;
  setActiveUrn: (urn: string | null) => void;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  language: LanguagePreference;
  setLanguage: (language: LanguagePreference) => void;
}

export const AppContext = createContext<AppContextValue | null>(null);

export function useAppContext(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used inside <Providers>.');
  return context;
}
