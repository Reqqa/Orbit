// The whole component kit, shared by every screen, so the dashboard reads as one
// product without pulling in a component library.

export function Card({ title, action, children, className = '' }) {
  return (
    <section
      className={`rounded-xl border border-[--color-line] bg-[--color-surface] ${className}`}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-[--color-line] px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Button({ variant = 'default', className = '', ...props }) {
  const styles = {
    primary: 'bg-[--color-brand] text-white hover:brightness-110',
    default: 'border border-[--color-line] bg-white hover:bg-[--color-canvas]',
    good: 'bg-[--color-good] text-white hover:brightness-110',
    danger: 'border border-[--color-bad] text-[--color-bad] hover:bg-[--color-bad-soft]',
    ghost: 'text-[--color-brand] hover:bg-[--color-brand-soft]',
  }[variant]

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    />
  )
}

const TONES = {
  neutral: 'bg-[--color-canvas] text-[--color-muted] border-[--color-line]',
  brand: 'bg-[--color-brand-soft] text-[--color-brand] border-transparent',
  good: 'bg-[--color-good-soft] text-[--color-good] border-transparent',
  warn: 'bg-[--color-warn-soft] text-[--color-warn] border-transparent',
  bad: 'bg-[--color-bad-soft] text-[--color-bad] border-transparent',
}

export function Badge({ tone = 'neutral', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

// One place decides what colour a classification or status is, so the meaning is
// consistent on every screen.
export function toneFor(value) {
  switch (value) {
    case 'EXACT_MATCH':
    case 'PAID':
    case 'APPROVED':
    case 'SENT':
      return 'good'
    case 'PARTIAL_PAYMENT':
    case 'PARTIAL':
    case 'MULTI_INVOICE':
    case 'LOW_CONFIDENCE':
    case 'PENDING':
    case 'DRAFT':
      return 'warn'
    case 'DUPLICATE':
    case 'OVERPAYMENT':
    case 'UNMATCHED':
    case 'NOT_A_RECEIPT':
    case 'REJECTED':
      return 'bad'
    default:
      return 'neutral'
  }
}

export function humanise(value) {
  if (!value) return ''
  return value.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())
}

export function Table({ columns, rows, renderRow, empty, onRowClick }) {
  if (!rows?.length) return <Empty>{empty}</Empty>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[--color-line] text-left text-xs uppercase tracking-wide text-[--color-muted]">
            {columns.map((column) => (
              <th key={column} className="py-2 pr-4 font-medium whitespace-nowrap">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={row.id ?? index}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-[--color-line] last:border-0 ${
                onRowClick ? 'cursor-pointer hover:bg-[--color-canvas]' : ''
              }`}
            >
              {renderRow(row)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Cell({ children, className = '' }) {
  return <td className={`py-2.5 pr-4 align-middle ${className}`}>{children}</td>
}

export function Empty({ children }) {
  return (
    <p className="rounded-lg border border-dashed border-[--color-line] px-4 py-8 text-center text-sm text-[--color-muted]">
      {children || 'Nothing here yet.'}
    </p>
  )
}

export function Bar({ value, max = 100, tone = 'brand' }) {
  const pct = Math.max(0, Math.min(100, max ? (value / max) * 100 : 0))
  const fill =
    { brand: 'var(--color-brand)', good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)' }[tone] ??
    'var(--color-brand)'
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-[--color-line]" role="presentation">
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: fill }} />
    </div>
  )
}

export function Loading({ what = 'Loading' }) {
  return <p className="px-1 py-8 text-sm text-[--color-muted]">{what}…</p>
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[--color-bad] bg-[--color-bad-soft] px-4 py-3 text-sm text-[--color-bad]">
      <span>{error.message || String(error)}</span>
      {onRetry && (
        <Button variant="ghost" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

// Shown wherever a simulated channel, hub or login is in play. Always visible,
// never dismissible: honesty about what is real is part of the product.
export function SimulatedNote({ children }) {
  return (
    <p className="rounded-lg border border-[--color-warn] bg-[--color-warn-soft] px-3 py-2 text-xs text-[--color-warn]">
      {children}
    </p>
  )
}
