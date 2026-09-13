import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Triadr - Self-Healing Multi-App Agent',
  description:
    'A multi-step AI agent across GitHub, Telegram and Stripe, with a reliability gate that retries, reroutes, deduplicates and rolls back so no workflow is left half-executed.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  )
}
