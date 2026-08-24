import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

const AUTH_STORAGE_KEY = 'metamind-auth-session';

export interface AuthUser {
  name: string;
  email: string;
  role: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  signIn: (email: string, password: string, username?: string) => Promise<void>;
  signOut: () => void;
}

const demoUsers: Array<AuthUser & { password: string }> = [
  {
    name: 'Admin',
    email: 'admin@metamind.ai',
    password: 'admin123',
    role: 'Platform Owner',
  },
  {
    name: 'Data Steward',
    email: 'steward@metamind.ai',
    password: 'steward123',
    role: 'Data Steward',
  },
];

const AuthContext = createContext<AuthContextValue | null>(null);

function loadSession(): AuthUser | null {
  if (typeof window === 'undefined') return null;

  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as AuthUser;
    if (!parsed?.email || !parsed?.name || !parsed?.role) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => loadSession());

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      signIn: async (email: string, password: string, username?: string) => {
        const normalizedEmail = email.trim().toLowerCase();
        const account = demoUsers.find(
          (entry) => entry.email.toLowerCase() === normalizedEmail && entry.password === password,
        );

        if (!account) {
          throw new Error('Invalid email or password. Try one of the demo accounts.');
        }

        const session: AuthUser = {
          name: username?.trim() || account.name,
          email: account.email,
          role: account.role,
        };

        setUser(session);
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
        }
      },
      signOut: () => {
        setUser(null);
        if (typeof window !== 'undefined') {
          window.localStorage.removeItem(AUTH_STORAGE_KEY);
        }
      },
    }),
    [user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within <AuthProvider>.');
  return context;
}
