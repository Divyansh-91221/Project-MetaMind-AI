import { useState } from 'react';
import type { ReactNode } from 'react';

/**
 * Confirmation gate for destructive or high-impact actions (demo reset, rejecting a
 * classification). Renders its trigger via `children` as a render prop so callers keep full
 * control over the button's look.
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel = 'Confirm',
  tone = 'danger',
  onConfirm,
  trigger,
}: {
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  tone?: 'danger' | 'primary';
  onConfirm: () => void | Promise<void>;
  trigger: (open: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    try {
      await onConfirm();
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {trigger(() => setOpen(true))}
      {open && (
        <div className="dialog-backdrop" role="presentation" onClick={() => !busy && setOpen(false)}>
          <div
            className="dialog"
            role="alertdialog"
            aria-modal="true"
            aria-label={title}
            onClick={(event) => event.stopPropagation()}
          >
            <h3>{title}</h3>
            <div className="muted small" style={{ marginBottom: 16 }}>
              {description}
            </div>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button type="button" className="button" disabled={busy} onClick={() => setOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className={`button ${tone === 'danger' ? 'danger' : 'primary'}`}
                disabled={busy}
                onClick={() => void confirm()}
              >
                {busy ? 'Working...' : confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
