import { Providers } from './providers';
import { AppRoutes } from './routes';
import { Layout } from '@/components/common/Layout';
import { AuthProvider, useAuth } from './authContext';
import { SignIn } from '@/pages/SignIn';

function Shell() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <SignIn />;
  }

  return (
    <Layout>
      <AppRoutes />
    </Layout>
  );
}

export function App() {
  return (
    <Providers>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </Providers>
  );
}
