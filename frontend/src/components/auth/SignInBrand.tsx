import styles from './signin.module.css';

const stats = [
  { value: '2.3M+', label: 'Metadata Assets' },
  { value: '15K+', label: 'Sensitive Columns' },
  { value: '4.9K+', label: 'Business Terms' },
  { value: '18K+', label: 'Lineage Relationships' },
];

export function SignInBrand() {
  return (
    <section className={styles.brandBlock} aria-label="MetaMind AI platform context">
      <p className={styles.kicker}>MetaMind AI</p>
      <h1 className={styles.brandTitle}>Enterprise Metadata Intelligence</h1>
      <p className={styles.brandMessage}>
        Discover, understand, govern and trust your enterprise data.
      </p>

      <dl className={styles.brandStats}>
        {stats.map((item) => (
          <div key={item.label} className={styles.statItem}>
            <dt className={styles.statValue}>{item.value}</dt>
            <dd className={styles.statLabel}>{item.label}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
