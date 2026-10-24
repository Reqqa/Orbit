'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { Badge, ErrorNote, Loading } from './ui'

// The eight screens, in the order the demo walks through them.
export const SCREENS = [
  { key: 'today', label: 'Today' },
  { key: 'approvals', label: 'Approvals' },
  { key: 'ledger', label: 'Ledger' },
  { key: 'chasing', label: 'Chasing' },
  { key: 'customers', label: 'Customers' },
  { key: 'audit', label: 'Audit log' },
  { key: 'simulator', label: 'WhatsApp simulator' },
  { key: 'settings', label: 'Settings' },
]

const OrbitContext = createContext(null)

/** Session, role and navigation, for any screen that needs them. */
export function useOrbit() {
  const value = useContext(OrbitContext)
  if (!value) throw new Error('useOrbit must be used inside the Shell')
  return value
}

export default function Shell({ children }) {
  const pathname = usePathname()
  const router = useRouter()
  const [session, setSession] = useState(null)
  const [users, setUsers] = useState([])
  const [error, setError] = useState(null)
  // Bumped after a role switch or an approval, so every screen refetches.
  const [version, setVersion] = useState(0)

  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  const loadSession = useCallback(async () => {
    try {
      setError(null)
      const [me, switchable] = await Promise.all([
        api.session(),
        api.switchableUsers().catch(() => []),
      ])
      setSession(me)
      setUsers(switchable)
    } catch (err) {
      setError(err)
    }
  }, [])

  useEffect(() => {
    loadSession()
  }, [loadSession])

  async function switchUser(userId) {
    await api.switchUser(Number(userId))
    await loadSession()
    refresh()
  }

  if (error) {
    return (
      <main className="mx-auto max-w-xl px-4 py-16">
        <h1 className="mb-3 text-lg font-semibold">Orbit cannot reach its API</h1>
        <ErrorNote error={error} onRetry={loadSession} />
        <p className="mt-4 text-sm text-[--color-muted]">
          Start the Python backend and seed the demo data:
        </p>
        <pre className="mt-2 overflow-x-auto rounded bg-white px-3 py-2 text-xs">
          cd backend{'\n'}python -m seed.generate_data --reset{'\n'}python -m seed.generate_receipts{'\n'}uvicorn app.main:app --reload
        </pre>
      </main>
    )
  }

  const current = pathname?.split('/').filter(Boolean)[0] ?? 'today'
  const value = {
    session,
    canApprove: session?.role === 'OWNER' || session?.role === 'FINANCE',
    goTo: (key) => router.push(`/${key}`),
    refresh,
    version,
  }

  return (
    <OrbitContext.Provider value={value}>
      <div className="min-h-full">
        <header className="border-b border-[--color-line] bg-[--color-surface]">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
            <Link href="/today" className="flex items-baseline gap-2">
              <span className="text-base font-semibold tracking-tight">Orbit</span>
              <span className="hidden text-xs text-[--color-muted] sm:inline">
                payment reconciliation for the Orbyte hub
              </span>
            </Link>

            <div className="ml-auto flex flex-wrap items-center gap-2">
              {session && (
                <>
                  <span className="text-xs text-[--color-muted]">{session.tenant_name}</span>
                  <Badge tone="brand">{session.role}</Badge>
                  <Badge tone="warn">Simulated login</Badge>
                  <select
                    aria-label="Switch user"
                    value={session.user_id}
                    onChange={(event) => switchUser(event.target.value)}
                    className="rounded-lg border border-[--color-line] bg-white px-2 py-1.5 text-sm"
                  >
                    {users.map((user) => (
                      <option key={user.user_id} value={user.user_id}>
                        {user.name} · {user.role} · {user.tenant_name}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </div>
          </div>

          <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-2 pb-2">
            {SCREENS.map((item) => (
              <Link
                key={item.key}
                href={`/${item.key}`}
                className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition ${
                  current === item.key
                    ? 'bg-[--color-brand-soft] font-medium text-[--color-brand]'
                    : 'text-[--color-muted] hover:bg-[--color-canvas]'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-6">
          {session ? children : <Loading what="Starting Orbit" />}
        </main>

        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-[--color-muted]">
          Synthetic data only. The WhatsApp channel, the Orbyte hub API and the login are
          simulated. Orbit records payments that already happened and never moves money.
        </footer>
      </div>
    </OrbitContext.Provider>
  )
}
