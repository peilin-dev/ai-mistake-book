export type IconName = 'pen' | 'book' | 'arrow' | 'search' | 'logout' | 'check' | 'print' | 'plus' | 'home' | 'users' | 'panel' | 'upload' | 'clipboard' | 'chart' | 'file' | 'layers' | 'chevron' | 'close'
const paths: Record<IconName, string> = {
  pen: 'm15 3 6 6-11 11-7 1 1-7L15 3Z M12 6l6 6 M4 14l6 6 M3 21l4-4',
  book: 'M12 5v15 M12 5C9 3 5 3 2 4v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Z',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  logout: 'M9 4H4v16h5 M10 12h11 M17 8l4 4-4 4',
  check: 'm5 12 4 4L19 6',
  plus: 'M12 5v14 M5 12h14',
  print:'M6 9V3h12v6 M6 17H3V9h18v8h-3 M6 14h12v7H6Z M17 11h1',
  home: 'm3 10 9-7 9 7v10H3Z M9 20v-7h6v7',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 4a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87',
  panel: 'M3 4h18v16H3Z M9 4v16',
  upload: 'M12 16V3 m-5 5 5-5 5 5 M4 15v6h16v-6',
  clipboard: 'M9 5H5v16h14V5h-4 M9 3h6v4H9Z m-1 11 3 3 5-6',
  chart: 'M4 3v18h17 M8 17v-5 M13 17V7 M18 17V4',
  file: 'M14 2H4v20h16V8Z M14 2v6h6 M8 12h8 M8 16h6',
  layers: 'm12 3 10 5-10 5L2 8Z M2 12l10 5 10-5 M2 16l10 5 10-5',
  chevron: 'm9 5 7 7-7 7',
  close: 'm6 6 12 12 M6 18 18 6',
}
export default function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
