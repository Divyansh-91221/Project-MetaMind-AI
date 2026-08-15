import type { ReactNode } from 'react';

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="state">
      <span className="spinner" aria-hidden /> <span className="muted">{`${label}...`}</span>
    </div>
  );
}

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state error">
      <div>{message}</div>
      {onRetry && (
        <button type="button" className="button" style={{ marginTop: 12 }} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="state">
      <div>{title}</div>
      {hint && <div className="faint small" style={{ marginTop: 6 }}>{hint}</div>}
    </div>
  );
}

/** Renders the standard loading / error / empty progression around fetched data. */
export function AsyncBoundary<T>({
  loading,
  error,
  data,
  onRetry,
  emptyTitle = 'Nothing to show yet.',
  children,
}: {
  loading: boolean;
  error: string | null;
  data: T | null;
  onRetry?: () => void;
  emptyTitle?: string;
  children: (data: T) => ReactNode;
}) {
  if (loading) return <Spinner />;
  if (error) return <ErrorMessage message={error} onRetry={onRetry} />;
  if (!data) return <EmptyState title={emptyTitle} />;
  return <>{children(data)}</>;
}
