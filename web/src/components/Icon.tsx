type Name = 'pen' | 'book' | 'arrow' | 'search' | 'logout' | 'check' | 'print'
const paths: Record<Name, string> = {
  pen: 'm15 3 6 6-11 11-7 1 1-7L15 3Z M12 6l6 6 M4 14l6 6 M3 21l4-4',
  book: 'M12 5v15 M12 5C9 3 5 3 2 4v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Z',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  logout: 'M9 4H4v16h5 M10 12h11 M17 8l4 4-4 4',
  check: 'm5 12 4 4L19 6',
  print: 'M6 9V3h12v6 M6 17H3V9h18v8h-3 M6 14h12v7H6Z M17 11h1',
}
export default function Icon({ name, size = 20 }: { name: Name; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
