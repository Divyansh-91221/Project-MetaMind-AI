import { useState } from 'react';
import { useAuth } from '@/app/authContext';
import { SignInBrand } from '@/components/auth/SignInBrand';
import { SignInCard } from '@/components/auth/SignInCard';
import { SignInGraph } from '@/components/auth/SignInGraph';
import styles from '@/components/auth/signin.module.css';

export function SignIn() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError(null);

    try {
      await signIn(email, password, username);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign in.');
    } finally {
      setPending(false);
    }
  };

  return (
    <main className={styles.signInPage}>
      <section className={styles.leftPanel}>
        <div className={styles.leftBackdrop} aria-hidden />
        <SignInGraph />
        <SignInBrand />
      </section>

      <section className={styles.rightPanel}>
        <SignInCard
          username={username}
          email={email}
          password={password}
          pending={pending}
          error={error}
          showPassword={showPassword}
          onUsernameChange={setUsername}
          onEmailChange={setEmail}
          onPasswordChange={setPassword}
          onTogglePassword={() => setShowPassword((value) => !value)}
          onSubmit={onSubmit}
        />
      </section>
    </main>
  );
}
