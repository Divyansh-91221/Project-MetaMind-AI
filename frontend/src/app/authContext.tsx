import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { AUTH_TOKEN_KEY } from '@/services/api';
import { authApi, type AuthUser } from '@/services/authApi';

const AUTH_STORAGE_KEY = 'metamind-auth-session';

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  signIn: (email: string, password: string, username?: string, register?: boolean) => Promise<void>;
  signOut: () => void;
}

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
      signIn: async (email, password, username, register = false) => {
        const response = register
          ? await authApi.register(username?.trim() || '', email, password)
          : await authApi.login(email, password);
        setUser(response.user);
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(AUTH_TOKEN_KEY, response.access_token);
          window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(response.user));
        }
      },
      signOut: () => {
        setUser(null);
        if (typeof window !== 'undefined') {
          window.localStorage.removeItem(AUTH_STORAGE_KEY);
          window.localStorage.removeItem(AUTH_TOKEN_KEY);
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
