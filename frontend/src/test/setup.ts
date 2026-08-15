import '@testing-library/jest-dom/vitest';

// jsdom has no fetch by default in some environments; individual tests stub it as needed.
if (!globalThis.fetch) {
  globalThis.fetch = (() =>
    Promise.reject(new Error('fetch must be mocked in tests'))) as typeof fetch;
}
