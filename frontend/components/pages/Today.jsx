'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import {
  Bar,
  Button,
  CapsuleChart,
  Card,
  ErrorNote,
  IconChip,
  Loading,
  SimulatedNote,
  StatCard,
} from '../ui'

export default function Today({ goTo }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      setData(await api.dashboard())
    } catch (err) {
      setError(err)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (error) return <ErrorNote error={error} onRetry={load} />
  if (!data) return <Loading what="Loading today" />

  const { cards, kpis, invoice_status: status } = data
  const pending = cards.needs_approval ?? 0

  const statuses = [
    { label: 'Open', value: status.OPEN ?? 0, color: 'var(--color-brand)' },
    { label: 'Partly paid', value: status.PARTIAL ?? 0, color: 'var(--color-accent)' },
    { label: 'Paid', value: status.PAID ?? 0, color: 'var(--color-ink)' },
  ]
  const invoiceTotal = statuses.reduce((sum, s) => sum + s.value, 0)

  return (
    <div className="space-y-4">
      {/* The three cards the whole screen exists for. The one that needs action
          carries the accent fill, so the eye lands on it first. */}
      <div className="grid gap-4 lg:grid-cols-3">
        <StatCard
          tone={pending > 0 ? 'accent' : 'surface'}
          icon="✓"
          label="Needs your approval"
          value={pending}
          ring={invoiceTotal ? Math.round((pending / invoiceTotal) * 100) : 0}
          hint={
            pending === 0
              ? 'Nothing is waiting on a decision right now.'
              : 'Payments Orbit matched to an invoice, waiting for you to confirm.'
          }
          meter={
            <div className="mt-4">
              <Bar
                value={pending}
                max={Math.max(10, pending)}
                tone="ink"
                segments={10}
                label="Waiting for approval"
              />
            </div>
          }
        />

        <StatCard
          icon="⏱"
          label="Overdue"
          value={cards.overdue_display}
          hint="Invoices past their due date and still unpaid."
          meter={
            <div className="mt-4">
              <Bar
                value={status.OPEN ?? 0}
                max={Math.max(1, invoiceTotal)}
                tone="bad"
                segments={10}
                label="Share of invoices still open"
              />
            </div>
          }
        />

        <StatCard
          icon="↓"
          label="Received this week"
          value={cards.received_week_display}
          hint="Payments approved and recorded in the last seven days."
          meter={
            <div className="mt-4">
              <Bar
                value={status.PAID ?? 0}
                max={Math.max(1, invoiceTotal)}
                tone="good"
                segments={10}
                label="Share of invoices paid"
              />
            </div>
          }
        />
      </div>

      {/* The single call to action, as prominent as the reference's. */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <IconChip tone="brand">→</IconChip>
            <div>
              <p className="text-sm font-medium">
                {pending === 0 ? 'Your inbox is clear' : `${pending} waiting for a decision`}
              </p>
              <p className="text-sm text-(--color-muted)">
                Each one shows the receipt, the invoice it matched, and why.
              </p>
            </div>
          </div>
          <Button
            variant="primary"
            disabled={pending === 0}
            onClick={() => goTo('approvals')}
            className="px-6 py-3 text-base"
          >
            {pending === 0 ? 'Nothing to review' : 'Review approvals'}
          </Button>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <Card title="Where the invoices stand">
          <CapsuleChart
            items={statuses.map((s) => ({ ...s, display: s.value }))}
            max={Math.max(1, ...statuses.map((s) => s.value))}
            legend={statuses.map((s) => ({ label: s.label, color: s.color }))}
          />
          <p className="mt-4 text-sm text-(--color-muted)">
            {invoiceTotal} invoices in total for this business.
          </p>
        </Card>

        <Card title="How the matching is doing">
          <dl className="space-y-5">
            <Rate
              label="Auto-match rate"
              pct={kpis.auto_match_rate}
              hint="Scored 90 or more against the right invoice."
            />
            <Rate
              label="Human corrections"
              pct={kpis.human_correction_rate}
              hint="Approvals where a person changed something first."
            />
            <div>
              <dt className="text-sm text-(--color-muted)">Receipts processed</dt>
              <dd className="mt-1 text-2xl font-medium tabular">{kpis.receipts_processed}</dd>
            </div>
            <div>
              <dt className="text-sm text-(--color-muted)">Still outstanding</dt>
              <dd className="mt-1 text-2xl font-medium tabular">{kpis.outstanding_display}</dd>
            </div>
          </dl>

          <p className="mt-5 text-xs text-(--color-muted)">
            About {kpis.seconds_per_receipt_orbit} seconds per receipt, against an{' '}
            <strong className="font-medium">assumed</strong>{' '}
            {Math.round(kpis.seconds_per_receipt_manual_assumed / 60)} minute manual baseline.
            The baseline is an assumption we have not yet measured, not a result.
          </p>
        </Card>
      </div>

      <SimulatedNote>
        Synthetic data. Send a receipt from the WhatsApp simulator to watch these numbers move.
      </SimulatedNote>
    </div>
  )
}

function Rate({ label, pct, hint }) {
  const value = Math.max(0, Math.min(100, Math.round(pct ?? 0)))
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <dt className="text-sm text-(--color-muted)">{label}</dt>
        <dd className="text-xl font-medium tabular">{value}%</dd>
      </div>
      <div className="mt-2">
        <Bar value={value} max={100} tone="brand" segments={10} label={label} />
      </div>
      <p className="mt-2 text-xs text-(--color-muted)">{hint}</p>
    </div>
  )
}
