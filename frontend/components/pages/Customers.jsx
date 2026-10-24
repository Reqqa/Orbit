'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import { Badge, Card, Cell, ErrorNote, Loading, SimulatedNote, Table } from '../ui'

function day(value) {
  return value ? String(value).slice(0, 10) : '—'
}

// Aliases arrive either as a list or as one comma-separated string; both read the
// same way to a human, so normalise once here.
function aliasList(aliases) {
  if (!aliases) return []
  const items = Array.isArray(aliases) ? aliases : String(aliases).split(',')
  return items.map((a) => String(a).trim()).filter(Boolean)
}

function flagList(flags) {
  if (!flags) return []
  const items = Array.isArray(flags) ? flags : String(flags).split(',')
  return items.map((f) => String(f).trim()).filter(Boolean)
}

export default function Customers() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)
  const [sort, setSort] = useState('balance')
  const [query, setQuery] = useState('')

  const load = useCallback(async () => {
    setErr(null)
    setRows(null)
    try {
      setRows(await api.customers())
    } catch (error) {
      setErr(error)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const visible = useMemo(() => {
    if (!rows) return []
    const needle = query.trim().toLowerCase()
    const matched = needle
      ? rows.filter(
          (row) =>
            String(row.name || '').toLowerCase().includes(needle) ||
            aliasList(row.aliases).some((alias) => alias.toLowerCase().includes(needle)),
        )
      : rows.slice()

    return matched.sort((a, b) =>
      sort === 'name'
        ? String(a.name || '').localeCompare(String(b.name || ''))
        : (b.balance_sen ?? 0) - (a.balance_sen ?? 0),
    )
  }, [rows, query, sort])

  const empty = query.trim()
    ? `No customer matches “${query.trim()}”. Try part of a nickname, or clear the search.`
    : 'No customers yet. Seed the demo data, or let a first receipt arrive in the WhatsApp simulator and Orbit will open a record.'

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">Customers</h1>
        <p className="mt-1 text-sm text-[--color-muted]">
          Who owes what, when they last paid, and how often they have been chased.
        </p>
      </div>

      <SimulatedNote>
        Synthetic customers. The WhatsApp channel these numbers belong to is simulated — no
        message ever leaves this machine.
      </SimulatedNote>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search a name or nickname"
          aria-label="Search customers by name or alias"
          className="w-full rounded-lg border border-[--color-line] bg-[--color-surface] px-3 py-2 text-sm sm:w-72"
        />
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-[--color-muted]">Sort</span>
          {[
            ['balance', 'Highest balance'],
            ['name', 'Name A–Z'],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setSort(key)}
              aria-pressed={sort === key}
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
                sort === key
                  ? 'bg-[--color-brand-soft] font-medium text-[--color-brand]'
                  : 'border border-[--color-line] bg-[--color-surface] text-[--color-muted] hover:bg-[--color-canvas]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {err && <ErrorNote error={err} onRetry={load} />}
      {!rows && !err && <Loading what="Loading customers" />}

      {rows && (
        <Card>
          <Table
            columns={['Customer', 'Balance', 'Last payment', 'Reminders sent', 'Language']}
            rows={visible}
            empty={empty}
            renderRow={(row) => (
              <>
                <Cell>
                  <span className="font-medium">{row.name}</span>
                  {aliasList(row.aliases).length > 0 && (
                    <span className="mt-0.5 block text-xs text-[--color-muted]">
                      also known as {aliasList(row.aliases).join(', ')}
                    </span>
                  )}
                  <span className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="tabular text-xs text-[--color-muted]">{row.phone_masked}</span>
                    {flagList(row.flags).map((flag) => (
                      <Badge key={flag} tone="bad">
                        {flag}
                      </Badge>
                    ))}
                  </span>
                </Cell>
                <Cell className="tabular whitespace-nowrap text-right font-medium">
                  {row.balance_display}
                </Cell>
                <Cell className="whitespace-nowrap">
                  {row.last_payment ? (
                    <>
                      <span className="tabular">{row.last_payment.amount_display}</span>
                      <span className="mt-0.5 block text-xs text-[--color-muted]">
                        {day(row.last_payment.paid_at)}
                      </span>
                    </>
                  ) : (
                    <span className="text-[--color-muted]">Never paid</span>
                  )}
                </Cell>
                <Cell className="tabular text-right">{row.reminders_sent ?? 0}</Cell>
                <Cell className="text-[--color-muted]">{row.language}</Cell>
              </>
            )}
          />
        </Card>
      )}

      <p className="text-xs text-[--color-muted]">
        Phone numbers are stored encrypted. Orbit only ever displays the last four digits, and
        nothing on this screen can reveal the rest.
      </p>
    </div>
  )
}
