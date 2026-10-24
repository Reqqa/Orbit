'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Button, Card, ErrorNote, Loading, SimulatedNote, humanise } from '../ui'

const LIMIT_KEY = 'finance_approval_limit_sen'
const inputBase =
  'w-full rounded-lg border border-[--color-line] bg-white px-3 py-2 text-sm disabled:bg-[--color-canvas] disabled:text-[--color-muted]'

function Fact({ label, children }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">{label}</p>
      <p className="mt-1 text-base font-medium">{children || '—'}</p>
    </div>
  )
}

// The settings blob comes from the seed script, so nothing here assumes a key.
// The value's own type picks the control.
function Field({ name, value, disabled, onChange }) {
  const label = humanise(name)
  const id = `setting-${name}`

  if (value !== null && typeof value === 'object') {
    return (
      <div className="sm:col-span-2">
        <label className="text-sm font-medium" htmlFor={id}>
          {label}
        </label>
        <pre
          id={id}
          className="mt-2 max-h-64 overflow-auto rounded-lg border border-[--color-line] bg-[--color-canvas] p-3 text-xs leading-relaxed"
        >
          {JSON.stringify(value, null, 2)}
        </pre>
        <p className="mt-1.5 text-xs text-[--color-muted]">
          Nested configuration is edited as JSON. This block is shown read-only here and saved
          back unchanged.
        </p>
      </div>
    )
  }

  if (typeof value === 'boolean') {
    return (
      <label className="flex items-center gap-3 text-sm font-medium" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={(event) => onChange(name, event.target.checked)}
          className="h-4 w-4 rounded border-[--color-line]"
        />
        {label}
      </label>
    )
  }

  const isNumber = typeof value === 'number'
  return (
    <div>
      <label className="text-sm font-medium" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type={isNumber ? 'number' : 'text'}
        step={isNumber ? 'any' : undefined}
        value={value ?? ''}
        disabled={disabled}
        onChange={(event) =>
          onChange(name, isNumber ? Number(event.target.value) : event.target.value)
        }
        className={`mt-2 ${inputBase}`}
      />
    </div>
  )
}

export default function Settings({ session, refresh }) {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState({})
  const [limitRinggit, setLimitRinggit] = useState('')
  const [err, setErr] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(null)

  const load = useCallback(async () => {
    try {
      setErr(null)
      setData(null)
      setSaved(null)
      const result = await api.settings()
      const blob = { ...(result.settings || {}) }
      const limitSen = result.finance_approval_limit_sen ?? blob[LIMIT_KEY] ?? 0
      delete blob[LIMIT_KEY]
      setData(result)
      setDraft(blob)
      setLimitRinggit(String((Number(limitSen) || 0) / 100))
    } catch (error) {
      setErr(error)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (err) return <ErrorNote error={err} onRetry={load} />
  if (!data) return <Loading what="Loading settings" />

  const editable = data.editable !== false
  const keys = Object.keys(draft)

  function change(name, value) {
    setSaved(null)
    setDraft((current) => ({ ...current, [name]: value }))
  }

  async function save() {
    setSaving(true)
    setSaved(null)
    try {
      setErr(null)
      const sen = Math.round((Number(limitRinggit) || 0) * 100)
      const result = await api.saveSettings({ settings: draft, finance_approval_limit_sen: sen })
      setSaved({ count: Object.keys(result.settings || draft).length, sen })
      refresh()
    } catch (error) {
      setErr(error)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          How Orbit matches receipts, chases customers and decides who may approve a payment.
        </p>
      </div>

      {!editable && (
        <p className="rounded-lg border border-[--color-warn] bg-[--color-warn-soft] px-4 py-3 text-sm text-[--color-warn]">
          Only the Owner can change settings. You are signed in as {humanise(session.role)}, so
          everything below is read-only.
        </p>
      )}

      <Card title="Business">
        <div className="grid gap-6 sm:grid-cols-3">
          <Fact label="Business name">{data.name}</Fact>
          <Fact label="WhatsApp number">{data.whatsapp_number}</Fact>
          <Fact label="Timezone">{data.timezone}</Fact>
        </div>
        <div className="mt-4">
          <SimulatedNote>
            The WhatsApp channel on this number is simulated. No message leaves this machine.
          </SimulatedNote>
        </div>
      </Card>

      <Card title="Finance approval limit">
        <label className="text-sm font-medium" htmlFor="limit">
          Most a Finance user may approve, in ringgit
        </label>
        <div className="mt-2 flex max-w-xs items-center gap-2">
          <span className="text-sm text-[--color-muted]">RM</span>
          <input
            id="limit"
            type="number"
            min="0"
            step="1"
            value={limitRinggit}
            disabled={!editable}
            onChange={(event) => {
              setSaved(null)
              setLimitRinggit(event.target.value)
            }}
            className={inputBase}
          />
        </div>
        <p className="mt-3 text-sm text-[--color-muted]">
          Lowering this changes who may approve the next payment immediately: anything above the
          limit goes to the Owner instead. Your own limit right now is{' '}
          {session.approval_limit_display}.
        </p>
      </Card>

      <Card title="Tenant configuration">
        {keys.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[--color-line] px-4 py-8 text-center text-sm text-[--color-muted]">
            This business has no saved configuration yet. Seed the demo data with{' '}
            <code>python -m seed.generate_data --reset</code> to get the match weights, confidence
            thresholds, chase ladder and quiet hours.
          </p>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2">
            {keys.map((key) => (
              <Field
                key={key}
                name={key}
                value={draft[key]}
                disabled={!editable}
                onChange={change}
              />
            ))}
          </div>
        )}
      </Card>

      <div className="flex flex-wrap items-center gap-4">
        <Button variant="primary" onClick={save} disabled={!editable || saving}>
          {saving ? 'Saving…' : 'Save settings'}
        </Button>
        {saved && (
          <p className="text-sm text-[--color-good]">
            Saved {saved.count} setting{saved.count === 1 ? '' : 's'} and a Finance approval limit
            of {saved.sen} sen.
          </p>
        )}
      </div>
    </div>
  )
}
