import { createContext, useContext } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';

export interface AppContextValue {
  /** The asset the user is currently looking at. Passed to the Copilot as page context. */
  activeUrn: string | null;
  setActiveUrn: (urn: string | null) => void;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
}

export const AppContext = createContext<AppContextValue | null>(null);

export function useAppContext(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used inside <Providers>.');
  return context;
}
