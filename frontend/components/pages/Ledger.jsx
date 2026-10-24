'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Badge, Button, Card, Cell, ErrorNote, Loading, Table, humanise, toneFor } from '../ui'

// Filter label -> the query string api.invoices() wants, plus the sentence the
// empty state should say when that filter is the reason the table is bare.
const FILTERS = [
  { key: 'all', label: 'All', params: '', empty: 'No invoices yet. Seed the demo data, or add an invoice from the Orbyte hub.' },
  { key: 'open', label: 'Open', params: '?status=OPEN', empty: 'No open invoices. Everything issued has been paid in full.' },
  { key: 'partial', label: 'Partial', params: '?status=PARTIAL', empty: 'No partially paid invoices. Every payment so far has settled its invoice exactly.' },
  { key: 'paid', label: 'Paid', params: '?status=PAID', empty: 'No paid invoices yet. Approve a matched receipt and it will land here.' },
  { key: 'overdue', label: 'Overdue only', params: '?overdue_only=true', empty: 'No overdue invoices. Every invoice is either paid or not due yet.' },
]

const DOT = { payment: '--color-good', reminder: '--color-warn', invoice_created: '--color-line' }

function day(value) {
  return value ? String(value).slice(0, 10) : '—'
}

export default function Ledger() {
  const [filter, setFilter] = useState('all')
  const [rows, setRows] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState(null)

  const active = FILTERS.find((f) => f.key === filter) ?? FILTERS[0]

  const load = useCallback(async () => {
    setErr(null)
    setRows(null)
    try {
      setRows(await api.invoices(active.params))
    } catch (error) {
      setErr(error)
    }
  }, [active.params])

  const loadDetail = useCallback(async () => {
    if (!openId) return
    setErr(null)
    setDetail(null)
    try {
      setDetail(await api.timeline(openId))
    } catch (error) {
      setErr(error)
    }
  }, [openId])

  useEffect(() => {
    load()
  }, [load])
  useEffect(() => {
    loadDetail()
  }, [loadDetail])

  // ---- One invoice's timeline -------------------------------------------------
  if (openId) {
    const invoice = detail?.invoice
    return (
      <div className="space-y-5">
        <Button variant="ghost" onClick={() => setOpenId(null)}>
          ← Back to the ledger
        </Button>

        {err && <ErrorNote error={err} onRetry={loadDetail} />}
        {!detail && !err && <Loading what="Loading this invoice" />}

        {invoice && (
          <Card
            title={`${invoice.invoice_no} · ${invoice.customer_name}`}
            action={<Badge tone={toneFor(invoice.status)}>{humanise(invoice.status)}</Badge>}
          >
            <dl className="mb-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              {[
                ['Issued', day(invoice.issue_date)],
                ['Due', day(invoice.due_date)],
                ['Total', invoice.total_display],
                ['Outstanding', invoice.outstanding_display],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs uppercase tracking-wide text-(--color-muted)">{label}</dt>
                  <dd className="tabular mt-1 font-medium">{value}</dd>
                </div>
              ))}
            </dl>

            {detail.events?.length ? (
              <ol className="space-y-5 border-l border-(--color-line) pl-5">
                {detail.events.map((event, index) => (
                  <li key={index} className="relative">
                    <span
                      className="absolute -left-[26px] top-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-(--color-surface)"
                      style={{ background: `var(${DOT[event.kind] ?? '--color-line'})` }}
                    />
                    <p className="text-xs text-(--color-muted)">{day(event.at)}</p>
                    <p className="mt-0.5 text-sm font-medium">{event.title}</p>
                    {event.detail && (
                      <p className="mt-0.5 text-sm text-(--color-muted)">{event.detail}</p>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="rounded-(--radius-inner) border border-dashed border-(--color-line) px-4 py-8 text-center text-sm text-(--color-muted)">
                Nothing has happened to this invoice since it was created. Send a reminder from
                Chasing, or receive a receipt in the simulator.
              </p>
            )}
          </Card>
        )}
      </div>
    )
  }

  // ---- The list --------------------------------------------------------------
  return (
    <div className="space-y-5">
      <div>
        <p className="mt-1 text-sm text-(--color-muted)">
          Every invoice and what is still owed on it. Click a row for its full history.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            onClick={() => setFilter(item.key)}
            aria-pressed={filter === item.key}
            className={`rounded-(--radius-inner) px-3 py-1.5 text-sm transition ${
              filter === item.key
                ? 'bg-(--color-brand-soft) font-medium text-(--color-brand)'
                : 'border border-(--color-line) bg-(--color-surface) text-(--color-muted) hover:bg-(--color-sunken)'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {err && <ErrorNote error={err} onRetry={load} />}
      {!rows && !err && <Loading what="Loading invoices" />}

      {rows && (
        <Card>
          <Table
            columns={['Invoice', 'Customer', 'Due', 'Total', 'Outstanding', 'Status']}
            rows={rows}
            empty={active.empty}
            onRowClick={(row) => setOpenId(row.id)}
            renderRow={(row) => (
              <>
                <Cell className="font-medium whitespace-nowrap">{row.invoice_no}</Cell>
                <Cell>{row.customer_name}</Cell>
                <Cell className="whitespace-nowrap text-(--color-muted)">
                  <span className="tabular">{day(row.due_date)}</span>
                  {row.days_overdue > 0 && (
                    <Badge tone="bad" className="ml-2">{row.days_overdue} days late</Badge>
                  )}
                </Cell>
                <Cell className="tabular text-right whitespace-nowrap">{row.total_display}</Cell>
                <Cell className="tabular text-right whitespace-nowrap">{row.outstanding_display}</Cell>
                <Cell>
                  <Badge tone={toneFor(row.status)}>{humanise(row.status)}</Badge>
                </Cell>
              </>
            )}
          />
        </Card>
      )}
    </div>
  )
}
