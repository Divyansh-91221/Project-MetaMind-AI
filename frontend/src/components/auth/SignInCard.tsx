import {
  CheckCircle2,
  Eye,
  EyeOff,
  Lock,
  Mail,
  User,
  ShieldCheck,
  Sparkles,
  LoaderCircle,
  Building2,
} from 'lucide-react';
import type { FormEvent } from 'react';
import styles from './signin.module.css';

interface SignInCardProps {
  username: string;
  email: string;
  password: string;
  pending: boolean;
  error: string | null;
  showPassword: boolean;
  onUsernameChange: (value: string) => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onTogglePassword: () => void;
  registerMode: boolean;
  onToggleMode: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}

export function SignInCard({
  username,
  email,
  password,
  pending,
  error,
  showPassword,
  onUsernameChange,
  onEmailChange,
  onPasswordChange,
  onTogglePassword,
  registerMode,
  onToggleMode,
  onSubmit,
}: SignInCardProps) {
  return (
    <section className={styles.cardWrap}>
      <div className={styles.cardGlow} aria-hidden />
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.logoMark} aria-hidden>
            <ShieldCheck size={18} />
          </span>
          <div>
            <p className={styles.logoText}>MetaMind AI</p>
            <h2 className={styles.welcome}>{registerMode ? 'Create your account' : 'Welcome back'}</h2>
            <p className={styles.subtitle}>
              {registerMode ? 'Set up your enterprise metadata workspace.' : 'Access your enterprise metadata workspace.'}
            </p>
          </div>
        </div>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          {registerMode ? (
            <>
              <label className={styles.inputLabel} htmlFor="auth-username">
                Full Name
              </label>
              <div className={styles.inputShell}>
                <User size={16} className={styles.inputIcon} aria-hidden />
                <input
                  id="auth-username"
                  className={styles.input}
                  type="text"
                  autoComplete="name"
                  value={username}
                  onChange={(event) => onUsernameChange(event.target.value)}
                  placeholder="Your name"
                  required
                  disabled={pending}
                />
              </div>
            </>
          ) : null}

          <label className={styles.inputLabel} htmlFor="auth-email">
            Work Email
          </label>
          <div className={styles.inputShell}>
            <Mail size={16} className={styles.inputIcon} aria-hidden />
            <input
              id="auth-email"
              className={styles.input}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => onEmailChange(event.target.value)}
              placeholder="name@company.com"
              required
              disabled={pending}
            />
          </div>

          <label className={styles.inputLabel} htmlFor="auth-password">
            Password
          </label>
          <div className={styles.inputShell}>
            <Lock size={16} className={styles.inputIcon} aria-hidden />
            <input
              id="auth-password"
              className={styles.input}
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder="Enter password"
              required
              disabled={pending}
            />
            <button
              className={styles.eyeToggle}
              type="button"
              onClick={onTogglePassword}
              disabled={pending}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}

          <button className={styles.submit} type="submit" disabled={pending}>
            {pending ? <LoaderCircle size={16} className={styles.spinner} aria-hidden /> : <Sparkles size={16} aria-hidden />}
            <span>{pending ? 'Authenticating...' : registerMode ? 'Create account' : 'Enter MetaMind'}</span>
          </button>

          <button className={styles.modeToggle} type="button" onClick={onToggleMode} disabled={pending}>
            {registerMode ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>

          <div className={styles.authChecks} aria-live="polite" aria-hidden={!pending}>
            <p className={styles.checkTitle}>Authenticating...</p>
            <ul>
              <li>
                <CheckCircle2 size={14} />
                Identity verified
              </li>
              <li>
                <CheckCircle2 size={14} />
                Workspace identified
              </li>
              <li>
                <CheckCircle2 size={14} />
                Access verified
              </li>
            </ul>
          </div>
        </form>

        <div className={styles.ssoSection}>
          <button type="button" className={styles.ssoButton} disabled aria-disabled="true" title="SSO setup pending">
            <Building2 size={16} aria-hidden />
            Continue with Microsoft
            <span className={styles.ssoTag}>Coming soon</span>
          </button>
          <button type="button" className={styles.ssoButton} disabled aria-disabled="true" title="SSO setup pending">
            <ShieldCheck size={16} aria-hidden />
            Continue with SSO
            <span className={styles.ssoTag}>Coming soon</span>
          </button>
        </div>

        <div className={styles.securityNote}>
          <p className={styles.securityTitle}>Enterprise-grade authentication</p>
          <p className={styles.securityText}>
            Your organization&apos;s data and metadata remain protected.
          </p>
        </div>
      </div>
    </section>
  );
}
