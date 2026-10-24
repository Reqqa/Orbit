'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { Badge, ErrorNote, IconChip, Loading } from './ui'

// The eight screens, in the order the demo walks through them. The glyph is what
// shows in the dark rail; the title is the oversized heading on the page.
export const SCREENS = [
  { key: 'today', label: 'Today', glyph: '◳', title: 'Today', lead: 'What needs you right now' },
  { key: 'approvals', label: 'Approvals', glyph: '✓', title: 'Approvals', lead: 'Receipts waiting for a decision' },
  { key: 'ledger', label: 'Ledger', glyph: '▤', title: 'Ledger', lead: 'Every invoice and where it stands' },
  { key: 'chasing', label: 'Chasing', glyph: '↻', title: 'Chasing', lead: 'Reminders, drafted and waiting for approval' },
  { key: 'customers', label: 'Customers', glyph: '☺', title: 'Customers', lead: 'Who owes what' },
  { key: 'audit', label: 'Audit log', glyph: '⛉', title: 'Audit log', lead: 'Who did what, and proof it was not edited' },
  { key: 'simulator', label: 'Simulator', glyph: '✆', title: 'WhatsApp simulator', lead: 'Send a receipt the way a customer would' },
  { key: 'settings', label: 'Settings', glyph: '⚙', title: 'Settings', lead: 'Limits, thresholds and the chase ladder' },
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
        <div className="rounded-[--radius-panel] bg-[--color-surface] p-8">
          <h1 className="mb-3 text-lg font-semibold">Orbit cannot reach its API</h1>
          <ErrorNote error={error} onRetry={loadSession} />
          <p className="mt-4 text-sm text-[--color-muted]">
            Start the Python backend and seed the demo data:
          </p>
          <pre className="mt-2 overflow-x-auto rounded-[--radius-inner] bg-[--color-sunken] px-4 py-3 text-xs">
            cd backend{'\n'}python -m seed.generate_data --reset{'\n'}python -m seed.generate_receipts{'\n'}uvicorn app.main:app --reload
          </pre>
        </div>
      </main>
    )
  }

  const current = pathname?.split('/').filter(Boolean)[0] ?? 'today'
  const screen = SCREENS.find((s) => s.key === current) ?? SCREENS[0]

  const value = {
    session,
    canApprove: session?.role === 'OWNER' || session?.role === 'FINANCE',
    goTo: (key) => router.push(`/${key}`),
    refresh,
    version,
  }

  return (
    <OrbitContext.Provider value={value}>
      <div className="flex min-h-full gap-3 p-3 sm:gap-4 sm:p-4">
        {/* The dark rail. Icons only on desktop; it folds into a scrolling strip
            on a phone so no screen becomes unreachable. */}
        <nav
          aria-label="Screens"
          className="sticky top-4 hidden h-[calc(100vh-2rem)] w-16 shrink-0 flex-col items-center gap-1 rounded-[--radius-panel] bg-[--color-rail] py-4 sm:flex"
        >
          <Link
            href="/today"
            aria-label="Orbit home"
            className="mb-3 flex h-10 w-10 items-center justify-center rounded-[--radius-inner] bg-[--color-accent] text-lg font-semibold text-[--color-ink]"
          >
            O
          </Link>

          {SCREENS.map((item) => (
            <Link
              key={item.key}
              href={`/${item.key}`}
              title={item.label}
              aria-label={item.label}
              aria-current={current === item.key ? 'page' : undefined}
              className={`flex h-10 w-10 items-center justify-center rounded-[--radius-inner] text-base transition ${
                current === item.key
                  ? 'bg-white text-[--color-ink]'
                  : 'text-white/55 hover:bg-white/10 hover:text-white'
              }`}
            >
              <span aria-hidden="true">{item.glyph}</span>
            </Link>
          ))}

          {session && (
            <span
              title={`${session.name} · ${session.role}`}
              className="mt-auto flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-sm font-medium text-white"
            >
              {session.name?.slice(0, 1)}
            </span>
          )}
        </nav>

        <div className="min-w-0 flex-1">
          <div className="rounded-[--radius-panel] bg-[--color-surface] p-5 sm:p-7">
            {/* Heading row: oversized title, with the role switcher kept at the
                top right exactly where the reference puts its primary action. */}
            <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <h1 className="display">{screen.title}</h1>
                <p className="mt-2 text-sm text-[--color-muted]">{screen.lead}</p>
              </div>

              {session && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="hidden text-xs text-[--color-muted] sm:inline">
                    {session.tenant_name}
                  </span>
                  <Badge tone="brand">{session.role}</Badge>
                  <Badge tone="warn">Simulated login</Badge>
                  <select
                    aria-label="Switch user"
                    value={session.user_id}
                    onChange={(event) => switchUser(event.target.value)}
                    className="rounded-full border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm"
                  >
                    {users.map((user) => (
                      <option key={user.user_id} value={user.user_id}>
                        {user.name} · {user.role} · {user.tenant_name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </header>

            {/* Phone navigation: the rail is hidden, so the screens live here. */}
            <div className="mb-6 flex gap-1.5 overflow-x-auto no-scrollbar sm:hidden">
              {SCREENS.map((item) => (
                <Link
                  key={item.key}
                  href={`/${item.key}`}
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-2 text-sm transition ${
                    current === item.key
                      ? 'bg-[--color-rail] font-medium text-white'
                      : 'bg-[--color-sunken] text-[--color-muted]'
                  }`}
                >
                  <span aria-hidden="true">{item.glyph}</span>
                  {item.label}
                </Link>
              ))}
            </div>

            {session ? children : <Loading what="Starting Orbit" />}
          </div>

          <footer className="px-5 py-5 text-xs text-[--color-muted]">
            <span className="inline-flex items-center gap-2">
              <IconChip tone="neutral" className="h-6 w-6 text-xs">
                i
              </IconChip>
              Synthetic data only. The WhatsApp channel, the Orbyte hub API and the login are
              simulated. Orbit records payments that already happened and never moves money.
            </span>
          </footer>
        </div>
      </div>
    </OrbitContext.Provider>
  )
}
