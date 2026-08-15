import { Providers } from './providers';
import { AppRoutes } from './routes';
import { Layout } from '@/components/common/Layout';

export function App() {
  return (
    <Providers>
      <Layout>
        <AppRoutes />
      </Layout>
    </Providers>
  );
}
