import Header from '../components/Header'

/** Temporary page body until tasks 6-8 replace the routes in App.tsx. */
export default function Placeholder({ title }: { title: string }) {
  return (
    <>
      <Header />
      <main style={{ padding: 24 }}>{title}</main>
    </>
  )
}