'use client'

import { Fragment, useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Button, Card, Cell, ErrorNote, Loading, SimulatedNote, humanise } from '../ui'

// Who did it decides the colour. The AI-vs-human distinction is the whole point of
// this screen, so it gets its own palette rather than reusing toneFor().
const ACTORS = [
  { key: '', label: 'All' },
  { key: 'USER', label: 'USER' },
  { key: 'SYSTEM', label: 'SYSTEM' },
  { key: 'AI', label: 'AI' },
  { key: 'CUSTOMER', label: 'CUSTOMER' },
]

const ACTOR_STYLE = {
  AI: 'bg-[--color-brand-soft] text-[--color-brand]',
  USER: 'bg-[--color-sunken] text-[--color-ink]',
  SYSTEM: 'bg-[--color-sunken] text-[--color-muted]',
  CUSTOMER: 'bg-[--color-warn-soft] text-[--color-warn]',
}

function ActorTag({ type, children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        ACTOR_STYLE[type] ?? ACTOR_STYLE.SYSTEM
      }`}
    >
      {children ?? type}
    </span>
  )
}

function when(value) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : '—'
}

export default function Audit() {
  const [actor, setActor] = useState('')
  const [text, setText] = useState('')
  const [rows, setRows] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [check, setCheck] = useState(null)
  const [checking, setChecking] = useState(false)
  const [err, setErr] = useState(null)

  const load = useCallback(async () => {
    setErr(null)
    setRows(null)
    try {
      setRows(await api.audit(actor ? `?actor_type=${encodeURIComponent(actor)}` : ''))
    } catch (error) {
      setErr(error)
    }
  }, [actor])

  useEffect(() => {
    load()
  }, [load])

  async function verify() {
    setChecking(true)
    setErr(null)
    try {
      setCheck(await api.verifyAudit())
    } catch (error) {
      setErr(error)
    } finally {
      setChecking(false)
    }
  }

  const needle = text.trim().toLowerCase()
  const visible = (rows ?? []).filter((row) =>
    !needle ||
    [row.action, row.actor_name, row.entity_type].some((field) =>
      String(field ?? '').toLowerCase().includes(needle),
    ),
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Audit log</h1>
        <p className="mt-1 text-sm text-[--color-muted]">
          Append-only and hash-chained. Every row carries the hash of the row before it, so
          changing one row anywhere breaks the chain from there onwards.
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={verify} disabled={checking}>
            {checking ? 'Verifying…' : 'Verify integrity'}
          </Button>
          <a
            href={api.auditExportUrl}
            download
            className="inline-flex items-center rounded-[--radius-inner] border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm font-medium hover:bg-[--color-sunken]"
          >
            Export .jsonl
          </a>
        </div>

        {check && (
          <div
            className={`mt-4 rounded-[--radius-inner] border p-4 ${
              check.ok
                ? 'border-[--color-good] bg-[--color-good-soft]'
                : 'border-[--color-bad] bg-[--color-bad-soft]'
            }`}
          >
            <p
              className={`text-base font-semibold ${
                check.ok ? 'text-[--color-good]' : 'text-[--color-bad]'
              }`}
            >
              {check.ok
                ? `Chain intact — ${check.rows_checked} rows checked.`
                : `Chain broken at row ${check.first_bad_id}.`}
            </p>
            {!check.ok && (
              <p className="mt-2 text-sm text-[--color-bad]">
                A row was changed after it was written. {check.detail}
              </p>
            )}
            {check.how_to_check_yourself && (
              <p className="mt-3 text-xs text-[--color-muted]">{check.how_to_check_yourself}</p>
            )}
          </div>
        )}
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Filter by action, person or entity"
          className="w-full rounded-[--radius-inner] border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm sm:w-72"
        />
        {ACTORS.map((item) => (
          <button
            key={item.key || 'all'}
            onClick={() => setActor(item.key)}
            aria-pressed={actor === item.key}
            className={`rounded-[--radius-inner] px-3 py-1.5 text-sm transition ${
              actor === item.key
                ? 'bg-[--color-brand-soft] font-medium text-[--color-brand]'
                : 'border border-[--color-line] bg-[--color-surface] text-[--color-muted] hover:bg-[--color-sunken]'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-[--color-muted]">
        <span>Who acted:</span>
        {['AI', 'USER', 'SYSTEM', 'CUSTOMER'].map((type) => (
          <ActorTag key={type} type={type} />
        ))}
      </div>

      <SimulatedNote>
        Actions logged by CUSTOMER arrived over the simulated WhatsApp channel, and USER rows
        are attributed through the simulated login.
      </SimulatedNote>

      {err && <ErrorNote error={err} onRetry={load} />}
      {!rows && !err && <Loading what="Loading the audit log" />}

      {rows && (
        <Card>
          {visible.length === 0 ? (
            <p className="rounded-[--radius-inner] border border-dashed border-[--color-line] px-4 py-8 text-center text-sm text-[--color-muted]">
              {needle || actor
                ? 'Nothing matches this filter. Clear the text box or pick All.'
                : 'The log is empty. Approve a receipt or run the chasing batch, then come back — every action writes a row here.'}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[--color-line] text-left text-xs uppercase tracking-wide text-[--color-muted]">
                    {['When', 'Who', 'Action', 'Entity'].map((column) => (
                      <th key={column} className="py-2 pr-4 font-medium whitespace-nowrap">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <Fragment key={row.id}>
                      <tr
                        onClick={() => setOpenId(openId === row.id ? null : row.id)}
                        className="cursor-pointer border-b border-[--color-line] hover:bg-[--color-sunken]"
                      >
                        <Cell className="tabular whitespace-nowrap text-[--color-muted]">
                          {when(row.created_at)}
                        </Cell>
                        <Cell className="whitespace-nowrap">
                          <ActorTag type={row.actor_type} />
                          <span className="ml-2">{row.actor_name || row.actor_id || '—'}</span>
                        </Cell>
                        <Cell className="font-medium">{humanise(row.action)}</Cell>
                        <Cell className="whitespace-nowrap text-[--color-muted]">
                          {humanise(row.entity_type)} #{row.entity_id}
                        </Cell>
                      </tr>
                      {openId === row.id && (
                        <tr className="border-b border-[--color-line]">
                          <td colSpan={4} className="bg-[--color-sunken] px-4 py-4">
                            <p className="font-mono text-xs text-[--color-muted]">
                              hash_self {String(row.hash_self ?? '').slice(0, 12)}…
                            </p>
                            <div className="mt-3 grid gap-4 sm:grid-cols-2">
                              {[
                                ['Before', row.before],
                                ['After', row.after],
                              ].map(([label, value]) => (
                                <div key={label}>
                                  <p className="text-xs uppercase tracking-wide text-[--color-muted]">
                                    {label}
                                  </p>
                                  <pre className="mt-1 overflow-x-auto rounded-[--radius-inner] border border-[--color-line] bg-[--color-surface] p-3 font-mono text-[11px] leading-relaxed">
                                    {value ?? '—'}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
