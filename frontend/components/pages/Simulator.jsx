'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Badge, Button, Card, Empty, ErrorNote, Loading, SimulatedNote, toneFor, humanise } from '../ui'

const MAX_BYTES = 5 * 1024 * 1024

const STEPS = [
  'Pick a customer on the left and attach a receipt photo, the way they would in WhatsApp.',
  'Orbit reads the image, matches it against open invoices and writes a proposal. It records nothing on its own.',
  'The proposal lands here, and in the approval inbox, for a human to approve or reject.',
]

function clock(iso) {
  const at = new Date(iso)
  return Number.isNaN(at.getTime()) ? '' : at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Simulator({ session, goTo }) {
  const [customers, setCustomers] = useState(null)
  const [customerId, setCustomerId] = useState('')
  const [thread, setThread] = useState([])
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [fileNote, setFileNote] = useState(null)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)
  const [sendError, setSendError] = useState(null)
  const [err, setErr] = useState(null)

  const load = useCallback(async () => {
    try {
      setErr(null)
      const rows = await api.customers()
      setCustomers(rows)
      setCustomerId((current) => current || String(rows[0]?.id ?? ''))
    } catch (error) {
      setErr(error)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const loadThread = useCallback(async (id) => {
    if (!id) return
    try {
      setThread(await api.simulatorThread(id))
    } catch (error) {
      setErr(error)
    }
  }, [])

  useEffect(() => {
    loadThread(customerId)
  }, [customerId, loadThread])

  function pickFile(event) {
    const chosen = event.target.files?.[0] ?? null
    if (chosen && chosen.size > MAX_BYTES) {
      setFile(null)
      setFileNote('That image is over 5 MB. WhatsApp would compress it, so pick a smaller photo.')
      event.target.value = ''
      return
    }
    setFileNote(null)
    setFile(chosen)
  }

  async function send(event) {
    event.preventDefault()
    const form = event.target
    setSending(true)
    setSendError(null)
    try {
      const sent = await api.simulatorSend(Number(customerId), file, text)
      setResult(sent)
      setText('')
      setFile(null)
      form.reset()
      await loadThread(customerId)
    } catch (error) {
      setSendError(error)
    } finally {
      setSending(false)
    }
  }

  if (err) return <ErrorNote error={err} onRetry={load} />
  if (!customers) return <Loading what="Loading the simulator" />

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-lg font-semibold">WhatsApp simulator</h1>
        <SimulatedNote>
          Simulated channel. Identical webhook payloads to the real WhatsApp Cloud API, so the
          pipeline being demonstrated is the one that ships.
        </SimulatedNote>
        <p className="text-sm text-[--color-muted]">
          Business number{' '}
          <span className="tabular font-medium text-[--color-ink]">
            {session.tenant_whatsapp_number || 'not configured'}
          </span>
        </p>
      </div>

      {customers.length === 0 ? (
        <Empty>
          No customers yet. Seed the demo data with
          {' '}
          <code>python -m seed.generate_data --reset</code>, then this screen will have someone to
          send from.
        </Empty>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="The customer's phone">
            <form onSubmit={send} className="space-y-3">
              <label className="block text-xs font-medium text-[--color-muted]">
                Sending as
                <select
                  value={customerId}
                  onChange={(event) => setCustomerId(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-[--color-line] bg-white px-3 py-2 text-sm text-[--color-ink]"
                >
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name} · {customer.balance_display} outstanding
                    </option>
                  ))}
                </select>
              </label>

              <label className="block text-xs font-medium text-[--color-muted]">
                Receipt photo
                <input
                  type="file"
                  accept="image/*"
                  onChange={pickFile}
                  className="mt-1 w-full rounded-lg border border-[--color-line] bg-white px-3 py-2 text-sm text-[--color-ink]"
                />
              </label>
              {fileNote && <SimulatedNote>{fileNote}</SimulatedNote>}

              <label className="block text-xs font-medium text-[--color-muted]">
                Message (optional)
                <input
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="Paid already boss"
                  className="mt-1 w-full rounded-lg border border-[--color-line] bg-white px-3 py-2 text-sm text-[--color-ink]"
                />
              </label>

              <Button type="submit" variant="primary" disabled={sending || !customerId}>
                {sending ? 'Sending…' : 'Send'}
              </Button>
              {sendError && <ErrorNote error={sendError} />}
            </form>

            <div className="mt-4 max-h-96 space-y-3 overflow-y-auto rounded-xl bg-[--color-canvas] p-3">
              {thread.length === 0 ? (
                <p className="py-6 text-center text-sm text-[--color-muted]">
                  Empty chat. Send a receipt above to start the conversation.
                </p>
              ) : (
                thread.map((message) => (
                  <div
                    key={message.id}
                    className={message.direction === 'OUT' ? 'flex justify-end' : 'flex justify-start'}
                  >
                    <div
                      className={`max-w-[80%] rounded-xl px-3 py-2 text-sm text-[--color-ink] ${
                        message.direction === 'OUT'
                          ? 'bg-[--color-good-soft]'
                          : 'border border-[--color-line] bg-[--color-surface]'
                      }`}
                    >
                      {message.media_url && (
                        <img
                          src={message.media_url}
                          alt="Receipt sent on WhatsApp"
                          className="mb-2 max-h-56 rounded-lg border border-[--color-line]"
                        />
                      )}
                      {message.text && <p className="whitespace-pre-wrap">{message.text}</p>}
                      <p className="mt-1 text-right text-xs text-[--color-muted]">
                        {clock(message.received_at)}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card title="The owner's phone">
            {result ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={toneFor(result.classification)}>
                    {humanise(result.classification) || 'No proposal'}
                  </Badge>
                  {result.confidence != null && (
                    <Badge>Confidence {Math.round(result.confidence)}%</Badge>
                  )}
                  {result.requested_approver_role && (
                    <Badge tone="brand">{result.requested_approver_role} must approve</Badge>
                  )}
                </div>
                <p className="text-sm text-[--color-muted]">
                  {result.proposal_id
                    ? 'Orbit has written a proposal and recorded nothing. A human decides what happens next.'
                    : 'Orbit did not raise a proposal for that message. Nothing was recorded.'}
                </p>
                <Button variant="primary" onClick={() => goTo('approvals')}>
                  Open the approval inbox
                </Button>
              </div>
            ) : (
              <ol className="space-y-3 text-sm text-[--color-muted]">
                {STEPS.map((step, index) => (
                  <li key={step} className="flex gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[--color-brand-soft] text-xs font-semibold text-[--color-brand]">
                      {index + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
