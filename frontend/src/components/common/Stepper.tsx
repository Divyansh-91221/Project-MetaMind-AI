import type { ReactNode } from 'react';

export interface StepperStep {
  label: string;
  detail?: ReactNode;
  state?: 'done' | 'active' | 'pending';
}

/**
 * Compact vertical stepper. Used for the Copilot reasoning trace and the AI Studio workflows -
 * both are "here is the sequence of real steps the system took", never free-form chain of
 * thought.
 */
export function Stepper({ steps }: { steps: StepperStep[] }) {
  return (
    <ol className="stepper">
      {steps.map((step, index) => (
        <li key={`${step.label}-${index}`} className={`stepper-item ${step.state ?? 'done'}`}>
          <span className="stepper-marker" aria-hidden>
            {step.state === 'pending' ? index + 1 : '\u2713'}
          </span>
          <div>
            <div className="stepper-label">{step.label}</div>
            {step.detail && <div className="stepper-detail faint small">{step.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function HealthScoreGauge({ total, label }: { total: number; label: string }) {
  const tone = total >= 85 ? 'ok' : total >= 70 ? 'default' : total >= 50 ? 'warn' : 'error';
  return (
    <div className={`health-gauge ${tone}`} title={`Health score: ${label}`}>
      <span className="health-gauge-value">{total}</span>
      <span className="health-gauge-max">/100</span>
    </div>
  );
}
