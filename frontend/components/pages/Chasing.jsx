'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Badge, Button, Card, Empty, ErrorNote, Loading, SimulatedNote, humanise } from '../ui'

// The rung decides how loud the message is, so it also decides the badge colour.
const rungTone = (rung) => (rung >= 7 ? 'bad' : rung >= 1 ? 'warn' : 'neutral')
const rungLabel = (rung) =>
  rung < 0 ? `Heads-up, ${Math.abs(rung)} days before due` : `Day +${rung} after due`

function DraftCard({ draft, kept, onToggle, canApprove }) {
  return (
    <Card className={kept ? '' : 'opacity-60'}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-base font-semibold">{draft.customer_name}</p>
          <p className="mt-0.5 text-sm text-[--color-muted]">
            {draft.invoice_no} · due {draft.due_date}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone={rungTone(draft.rung)}>{rungLabel(draft.rung)}</Badge>
            <Badge>{humanise(draft.tone)} tone</Badge>
            <Badge>{draft.language}</Badge>
            <span className="text-xs text-[--color-muted]">{draft.template_id}</span>
          </div>
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold tracking-tight tabular">{draft.outstanding_display}</p>
          <p className="text-xs text-[--color-muted]">outstanding</p>
        </div>
      </div>

      <blockquote className="mt-4 whitespace-pre-wrap rounded-lg border-l-4 border-[--color-brand] bg-[--color-canvas] px-4 py-3 text-sm">
        {draft.body}
      </blockquote>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-[--color-muted]">
          {kept ? 'Will be sent when the batch is approved.' : 'Skipped — nothing will be sent.'}
        </span>
        {canApprove ? (
          <Button variant={kept ? 'default' : 'ghost'} onClick={() => onToggle(draft.id)}>
            {kept ? 'Skip this one' : 'Keep it after all'}
          </Button>
        ) : (
          <Badge tone="neutral">Read-only</Badge>
        )}
      </div>
    </Card>
  )
}

export default function Chasing({ session, canApprove, refresh }) {
  const [batch, setBatch] = useState(null)
  const [skipped, setSkipped] = useState([]) // ids toggled off by hand
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)
  const [sentNote, setSentNote] = useState(null)

  const load = useCallback(async () => {
    setErr(null)
    try {
      setBatch(await api.chaseBatch())
      setSkipped([])
    } catch (e) {
      setErr(e)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function runNow() {
    setBusy('run')
    setErr(null)
    setSentNote(null)
    try {
      setBatch(await api.chaseRunNow())
      setSkipped([])
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(null)
    }
  }

  async function approve() {
    setBusy('approve')
    setErr(null)
    const keep = (batch.drafts || []).map((d) => d.id).filter((id) => !skipped.includes(id))
    try {
      const result = await api.chaseApprove(batch.date, keep, skipped)
      setSentNote(result)
      await load()
      refresh()
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(null)
    }
  }

  if (err && !batch) return <ErrorNote error={err} onRetry={load} />
  if (!batch) return <Loading what="Working out today's reminders" />

  const drafts = batch.drafts || []
  const keptIds = drafts.map((d) => d.id).filter((id) => !skipped.includes(id))
  const toggle = (id) =>
    setSkipped((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Chasing</h1>
          <p className="mt-1 text-sm text-[--color-muted]">
            Reminder batch for {batch.date}. Nothing leaves Orbit until you approve it.
          </p>
        </div>
        <Button variant="default" onClick={runNow} disabled={busy === 'run'}>
          {busy === 'run' ? 'Running…' : 'Run now'}
        </Button>
      </div>

      <SimulatedNote>
        Reminders go out over the simulated WhatsApp channel from{' '}
        {session.tenant_whatsapp_number}. No real message is delivered.
      </SimulatedNote>

      {batch.note && <p className="text-sm text-[--color-muted]">{batch.note}</p>}
      {batch.quiet_hours_now && (
        <SimulatedNote>
          It is outside quiet hours (9am–8pm), so reminders are normally held until morning.
          {batch.held_for_quiet_hours ? ` ${batch.held_for_quiet_hours} held right now.` : ''}
        </SimulatedNote>
      )}
      {err && <ErrorNote error={err} onRetry={load} />}
      {sentNote && (
        <p className="rounded-lg border border-[--color-good] bg-[--color-good-soft] px-4 py-3 text-sm text-[--color-good]">
          Sent {sentNote.sent} reminder{sentNote.sent === 1 ? '' : 's'}, skipped{' '}
          {sentNote.skipped}.{sentNote.simulated ? ' Simulated channel.' : ''}
        </p>
      )}
      {!canApprove && (
        <p className="text-sm text-[--color-muted]">
          You are signed in as {humanise(session.role)}. Only an Owner or Finance user may
          approve a reminder batch, so this screen is read-only for you.
        </p>
      )}

      <div className="space-y-4">
        <h2 className="text-sm font-semibold">Drafts ({drafts.length})</h2>
        {drafts.length === 0 ? (
          <Empty>
            No reminders are due today. Press “Run now” after a due date passes, or open the
            Ledger to check which invoices are still open.
          </Empty>
        ) : (
          drafts.map((draft) => (
            <DraftCard
              key={draft.id}
              draft={draft}
              kept={!skipped.includes(draft.id)}
              onToggle={toggle}
              canApprove={canApprove}
            />
          ))
        )}
      </div>

      {canApprove && drafts.length > 0 && (
        <div className="sticky bottom-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[--color-line] bg-[--color-surface] px-4 py-3">
          <span className="text-sm text-[--color-muted]">
            {keptIds.length} kept · {skipped.length} skipped by hand
          </span>
          <Button variant="primary" onClick={approve} disabled={busy === 'approve' || !keptIds.length}>
            {busy === 'approve'
              ? 'Sending…'
              : `Send ${keptIds.length} reminder${keptIds.length === 1 ? '' : 's'}`}
          </Button>
        </div>
      )}

      <Card title="Skipped, and why">
        <p className="mb-3 text-sm text-[--color-muted]">
          Orbit holds a reminder back when chasing would be wrong — a payment is already
          waiting for approval, the customer is disputed or promised a date, or we messaged
          them in the last three days.
        </p>
        {batch.skipped?.length ? (
          <ul className="space-y-2 text-sm">
            {batch.skipped.map((row, i) => (
              <li key={i} className="border-b border-[--color-line] pb-2 last:border-0 last:pb-0">
                <span className="font-medium">{row.customer}</span>{' '}
                <span className="text-[--color-muted]">{row.invoice_no}</span>
                <p className="text-[--color-muted]">{row.reason}</p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Nothing was held back today. Every guard passed.</Empty>
        )}
      </Card>

      <Card title="Owner tasks — please call, do not message">
        <p className="mb-3 text-sm text-[--color-muted]">
          Once an invoice is fourteen days late, Orbit deliberately sends no automatic
          message. A relationship that old needs a phone call from you, not another template.
        </p>
        {batch.owner_tasks?.length ? (
          <ul className="space-y-3 text-sm">
            {batch.owner_tasks.map((row, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 border-b border-[--color-line] pb-3 last:border-0 last:pb-0">
                <span className="font-medium">{row.customer}</span>
                <span className="text-[--color-muted]">{row.invoice_no}</span>
                <span className="tabular font-medium">{row.outstanding_display}</span>
                <p className="w-full text-[--color-muted]">{row.task}</p>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No invoice is fourteen days late. Nothing for you to call about.</Empty>
        )}
      </Card>
    </div>
  )
}
