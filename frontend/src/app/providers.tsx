import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { createContext, useContext, useMemo, useState } from 'react';

interface AppContextValue {
  /** The asset the user is currently looking at. Passed to the Copilot as page context. */
  activeUrn: string | null;
  setActiveUrn: (urn: string | null) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function useAppContext(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used inside <Providers>.');
  return context;
}

/**
 * Application-wide providers.
 *
 * Currently routing plus a tiny context for the active asset. This is the seam where an auth
 * provider, a query client and a theme provider will be added.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [activeUrn, setActiveUrn] = useState<string | null>(null);
  const value = useMemo(() => ({ activeUrn, setActiveUrn }), [activeUrn]);

  return (
    <BrowserRouter>
      <AppContext.Provider value={value}>{children}</AppContext.Provider>
    </BrowserRouter>
  );
}
