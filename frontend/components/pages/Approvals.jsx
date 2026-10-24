'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Badge, Bar, Button, Card, ErrorNote, Loading, SimulatedNote, humanise, toneFor } from '../ui'

const LOW = 0.7

function Field({ label, value, confidence }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 border-b border-[--color-line] py-1.5 last:border-0">
      <dt className="w-40 shrink-0 text-xs uppercase tracking-wide text-[--color-muted]">{label}</dt>
      <dd className="text-sm">
        {value || <span className="text-[--color-muted]">not found</span>}
        {confidence != null && confidence < LOW && (
          <span className="ml-2 rounded-full bg-[--color-warn-soft] px-2 py-0.5 text-[11px] font-medium text-[--color-warn]">
            please check
          </span>
        )}
      </dd>
    </div>
  )
}

function ApprovalCard({ item, canApprove, onDone }) {
  const [mode, setMode] = useState(null) // null | 'reject' | 'edit'
  const [note, setNote] = useState('')
  const [amount, setAmount] = useState('')
  const [invoiceId, setInvoiceId] = useState(item.candidates?.[0]?.invoice_id ?? '')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const ex = item.extracted || {}
  const fc = ex.field_confidence || {}
  const story = item.explanation || {}
  const top = item.candidates?.[0]

  async function decide(decision, text, edits) {
    setBusy(decision)
    setErr(null)
    try {
      await api.decide(item.id, decision, text, edits)
      onDone()
    } catch (e) {
      setErr(e) // the card stays put: a 403 is the demo, not a crash
    } finally {
      setBusy(null)
    }
  }

  function submitEdit() {
    const sen = Math.round(parseFloat(amount) * 100)
    if (!Number.isFinite(sen) || sen <= 0) {
      setErr(new Error('Enter an amount in ringgit, like 850.00'))
      return
    }
    if (!invoiceId) {
      setErr(new Error('Pick an invoice to allocate to.'))
      return
    }
    decide('approve', note || 'Corrected by hand', {
      amount_sen: sen,
      allocations: [{ invoice_id: invoiceId, amount_sen: sen }],
    })
  }

  return (
    <Card>
      <div className="grid gap-6 md:grid-cols-[2fr_3fr]">
        <div className="space-y-3">
          {item.media_url ? (
            <img
              src={item.media_url}
              alt="Payment receipt as received on WhatsApp"
              className="w-full rounded-[--radius-inner] border border-[--color-line] bg-[--color-sunken] object-contain"
            />
          ) : (
            <div className="flex h-56 items-center justify-center rounded-[--radius-inner] border border-dashed border-[--color-line] bg-[--color-sunken] px-4 text-center text-sm text-[--color-muted]">
              No image came with this message.
            </div>
          )}
          {item.simulated_channel && (
            <SimulatedNote>Arrived over the simulated WhatsApp channel.</SimulatedNote>
          )}
        </div>

        <div className="space-y-5">
          <div>
            <p className="text-sm text-[--color-muted]">
              {item.customer?.name || 'Unknown sender'} · suggests {top?.invoice_no || 'no invoice'}
            </p>
            <p className="mt-1 text-4xl font-semibold tracking-tight tabular">{item.amount_display}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge tone={toneFor(item.classification)}>{humanise(item.classification)}</Badge>
              <span className="text-xs text-[--color-muted]">
                needs {humanise(item.requested_approver_role)}
              </span>
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-baseline justify-between text-xs text-[--color-muted]">
              <span>{story.confidence_label || 'Confidence'}</span>
              <span className="tabular">{Math.round(item.confidence ?? 0)}%</span>
            </div>
            <Bar value={item.confidence ?? 0} tone={toneFor(item.classification)} />
          </div>

          <div>
            <h3 className="text-sm font-semibold">Why we think so</h3>
            {story.headline && <p className="mt-1 text-sm text-[--color-muted]">{story.headline}</p>}
            <ul className="mt-2 space-y-1 text-sm">
              {(story.matched || []).map((line, i) => (
                <li key={`m${i}`} className="flex gap-2">
                  <span className="text-[--color-good]">✓</span>
                  <span>{line}</span>
                </li>
              ))}
              {(story.missing || []).map((line, i) => (
                <li key={`x${i}`} className="flex gap-2 text-[--color-warn]">
                  <span aria-hidden="true">!</span>
                  <span>Please confirm: {line}</span>
                </li>
              ))}
            </ul>
          </div>

          <dl>
            <Field label="Amount read" value={ex.amount} confidence={fc.amount} />
            <Field label="Date and time" value={ex.transaction_datetime} confidence={fc.date} />
            <Field label="Payer" value={ex.payer_name} confidence={fc.payer_name} />
            <Field label="Payee" value={ex.payee_name} />
            <Field label="Bank or wallet" value={ex.bank_or_wallet || ex.channel} />
            <Field label="Reference" value={ex.reference_text} confidence={fc.reference_text} />
            <Field label="Transaction ID" value={ex.transaction_id} />
          </dl>

          {story.next_step && <p className="text-sm font-medium">{story.next_step}</p>}
          <p className="text-xs text-[--color-muted]">Read by {item.model_name || 'the extractor'}.</p>

          {err && <ErrorNote error={err} />}

          <div className="flex flex-wrap gap-2">
            <Button variant="good" disabled={!!busy} onClick={() => decide('approve', note || null)}>
              {busy === 'approve' ? 'Approving…' : 'Approve'}
            </Button>
            <Button disabled={!!busy} onClick={() => setMode(mode === 'edit' ? null : 'edit')}>
              Edit
            </Button>
            <Button
              variant="danger"
              disabled={!!busy}
              onClick={() => setMode(mode === 'reject' ? null : 'reject')}
            >
              {busy === 'reject' ? 'Rejecting…' : 'Reject'}
            </Button>
          </div>

          {!canApprove && (
            <p className="text-xs text-[--color-muted]">
              Your role cannot approve payments. The buttons stay here so you can see what the
              server says, and the attempt is written to the audit log.
            </p>
          )}

          {mode === 'reject' && (
            <div className="space-y-2 rounded-[--radius-inner] border border-[--color-line] bg-[--color-sunken] p-3">
              <label className="block text-xs font-medium" htmlFor={`reject-${item.id}`}>
                Why are you rejecting this? Required.
              </label>
              <textarea
                id={`reject-${item.id}`}
                rows={2}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-[--radius-inner] border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm"
                placeholder="Receipt belongs to an older invoice"
              />
              <Button
                variant="danger"
                disabled={!!busy || note.trim().length < 3}
                onClick={() => decide('reject', note.trim())}
              >
                Confirm rejection
              </Button>
            </div>
          )}

          {mode === 'edit' && (
            <div className="space-y-3 rounded-[--radius-inner] border border-[--color-line] bg-[--color-sunken] p-3">
              <div>
                <label className="block text-xs font-medium" htmlFor={`amount-${item.id}`}>
                  Correct amount in ringgit
                </label>
                <input
                  id={`amount-${item.id}`}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  inputMode="decimal"
                  placeholder="850.00"
                  className="mt-1 w-40 rounded-[--radius-inner] border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm tabular"
                />
              </div>
              <div>
                <label className="block text-xs font-medium" htmlFor={`invoice-${item.id}`}>
                  Allocate to invoice
                </label>
                <select
                  id={`invoice-${item.id}`}
                  value={invoiceId}
                  onChange={(e) => setInvoiceId(e.target.value)}
                  className="mt-1 w-full rounded-[--radius-inner] border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm"
                >
                  {(item.candidates || []).map((c) => (
                    <option key={c.invoice_id} value={c.invoice_id}>
                      {c.invoice_no} · score {c.score}
                    </option>
                  ))}
                </select>
              </div>
              <Button variant="primary" disabled={!!busy} onClick={submitEdit}>
                {busy === 'approve' ? 'Saving…' : 'Approve with my corrections'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

export default function Approvals({ session, canApprove, goTo, refresh }) {
  const [items, setItems] = useState(null)
  const [err, setErr] = useState(null)

  const load = useCallback(async () => {
    try {
      setErr(null)
      setItems(await api.approvals('PENDING'))
    } catch (e) {
      setErr(e)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (err) return <ErrorNote error={err} onRetry={load} />
  if (!items) return <Loading what="Loading approvals" />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Needs your approval</h1>
        <p className="mt-1 text-sm text-[--color-muted]">
          {items.length === 0
            ? 'Every receipt has been dealt with.'
            : `${items.length} receipt${items.length === 1 ? '' : 's'} read and waiting on a human. Nothing is recorded until you decide.`}
          {session?.approval_limit_display ? ` Your limit is ${session.approval_limit_display}.` : ''}
        </p>
      </div>

      {items.length === 0 ? (
        <Card>
          <div className="px-2 py-10 text-center">
            <p className="text-base font-medium">Nothing waiting for you.</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-[--color-muted]">
              Send a receipt from the WhatsApp simulator and it will land here within seconds.
            </p>
            <div className="mt-4">
              <Button variant="ghost" onClick={() => goTo('simulator')}>
                Open the WhatsApp simulator
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        items.map((item) => (
          <ApprovalCard key={item.id} item={item} canApprove={canApprove} onDone={refresh} />
        ))
      )}
    </div>
  )
}
