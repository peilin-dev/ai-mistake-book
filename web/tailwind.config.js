export default {
  content: ['./src/pages/Landing.tsx'],
  prefix: 'tw-',
  corePlugins: { preflight: false },
  theme: { extend: { colors: { brand: 'var(--link)', ink: 'var(--ink)', muted: 'var(--ink-2)', paper: 'var(--paper)' } } },
}
