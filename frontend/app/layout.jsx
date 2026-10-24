import Shell from '@/components/Shell'
import './globals.css'

export const metadata = {
  title: 'Orbit',
  description: 'Orbit, payment reconciliation for the Orbyte hub.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  )
}
