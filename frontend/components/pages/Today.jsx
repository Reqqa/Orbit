'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Bar, Button, Card, ErrorNote, Loading, SimulatedNote } from '../ui'

// One big number with a plain-English line under it. Readable across a room.
function BigCard({ label, value, hint, tone = 'ink', huge = false }) {
  const colour = { ink: 'text-[--color-ink]', bad: 'text-[--color-bad]', good: 'text-[--color-good]' }[tone]
  return (
    <Card className="p-2">
      <p className="text-sm font-medium text-[--color-muted]">{label}</p>
      <p className={`mt-3 font-semibold tracking-tight ${colour} ${huge ? 'text-6xl' : 'text-4xl'}`}>
        {value}
      </p>
      <p className="mt-3 text-sm text-[--color-muted]">{hint}</p>
    </Card>
  )
}

function Rate({ label, pct, tone }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-[--color-muted]">{label}</span>
        <span className="text-xl font-semibold tabular">{pct}%</span>
      </div>
      <div className="mt-2">
        <Bar value={pct} max={100} tone={tone} />
      </div>
    </div>
  )
}

function StatusBar({ label, count, total, tone }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-[--color-muted]">{label}</span>
        <span className="text-lg font-semibold tabular">{count}</span>
      </div>
      <div className="mt-2">
        <Bar value={count} max={total || 1} tone={tone} />
      </div>
    </div>
  )
}

export default function Today({ session, goTo }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  const load = useCallback(async () => {
    try {
      setErr(null)
      setData(null)
      setData(await api.dashboard())
    } catch (error) {
      setErr(error)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (err) return <ErrorNote error={err} onRetry={load} />
  if (!data) return <Loading what="Loading today" />

  const { cards, kpis, invoice_status: mix } = data
  const pending = cards.needs_approval
  const statusTotal = (mix?.OPEN || 0) + (mix?.PARTIAL || 0) + (mix?.PAID || 0)
  const manualMinutes = Math.round(kpis.seconds_per_receipt_manual_assumed / 60)

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Good day, {session.name.split(' ')[0]}
        </h1>
        <p className="mt-1 text-sm text-[--color-muted]">
          {session.tenant_name} · everything waiting on you is on this screen.
        </p>
      </div>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <BigCard
          huge
          label="Needs your approval"
          value={pending}
          hint={
            pending === 0
              ? 'No payments are waiting on a decision right now.'
              : 'Payments Orbit matched to an invoice, waiting for you to confirm.'
          }
        />
        <BigCard
          label="Overdue"
          tone={cards.overdue_sen > 0 ? 'bad' : 'ink'}
          value={cards.overdue_display}
          hint="Invoices past their due date and still unpaid."
        />
        <BigCard
          label="Received this week"
          tone="good"
          value={cards.received_week_display}
          hint="Payments confirmed in the last seven days."
        />
      </div>

      <div>
        <Button
          variant="primary"
          disabled={pending === 0}
          onClick={() => goTo('approvals')}
          className="w-full px-8 py-5 text-lg sm:w-auto"
        >
          {pending === 0 ? 'Nothing to review' : `Review approvals (${pending})`}
        </Button>
        {pending === 0 && (
          <p className="mt-3 text-sm text-[--color-muted]">
            When a customer sends a receipt on WhatsApp it appears here for approval. Try it
            from the WhatsApp simulator.
          </p>
        )}
      </div>

      <Card title="How Orbit is doing">
        <div className="grid gap-6 sm:grid-cols-2">
          <Rate label="Auto-match rate" pct={kpis.auto_match_rate} tone="good" />
          <Rate label="Human-correction rate" pct={kpis.human_correction_rate} tone="warn" />
          <div>
            <p className="text-sm text-[--color-muted]">Receipts processed</p>
            <p className="mt-1 text-3xl font-semibold tabular">{kpis.receipts_processed}</p>
          </div>
          <div>
            <p className="text-sm text-[--color-muted]">Total outstanding</p>
            <p className="mt-1 text-3xl font-semibold tabular">{kpis.outstanding_display}</p>
          </div>
        </div>
        <p className="mt-6 border-t border-[--color-line] pt-4 text-sm text-[--color-muted]">
          Orbit handles a receipt in about {kpis.seconds_per_receipt_orbit} seconds, against an
          assumed {manualMinutes} minute manual baseline. The manual figure is an assumption we
          chose, not something Orbit measured.
        </p>
      </Card>

      <Card title="Where the invoices stand">
        {statusTotal === 0 ? (
          <p className="text-sm text-[--color-muted]">
            No invoices yet. Load an invoice list, or seed the demo data, and this mix fills in.
          </p>
        ) : (
          <div className="space-y-5">
            <StatusBar label="Open" count={mix.OPEN} total={statusTotal} tone="brand" />
            <StatusBar label="Partly paid" count={mix.PARTIAL} total={statusTotal} tone="warn" />
            <StatusBar label="Paid" count={mix.PAID} total={statusTotal} tone="good" />
            <p className="text-sm text-[--color-muted]">{statusTotal} invoices in total.</p>
          </div>
        )}
      </Card>

      <SimulatedNote>
        Demo build: the WhatsApp channel, the Orbyte hub API and your login are simulated, and all
        data here is synthetic. Orbit records payments that already happened; it never moves money.
      </SimulatedNote>
    </div>
  )
}
