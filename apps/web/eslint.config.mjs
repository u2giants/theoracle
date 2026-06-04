// ESLint flat config (ESLint 9 / Next 16).
//
// Next 16 removed the `next lint` subcommand and ships `eslint-config-next` as
// a native flat config. We import it directly (no FlatCompat — that path hits a
// circular-structure bug with eslint-config-next v16). Replaces .eslintrc.json,
// which previously did `extends: next/core-web-vitals` + the one rule override.

import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

const eslintConfig = [
  // Don't lint build output / deps / generated type shims.
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'] },
  ...nextCoreWebVitals,
  {
    rules: {
      '@next/next/no-html-link-for-pages': 'off',
    },
  },
];

export default eslintConfig;
