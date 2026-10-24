// The whole component kit, shared by every screen, so the dashboard reads as one
// product without pulling in a component library.
//
// House style: soft canvas, floating white panels, very round corners, pill
// controls, near-black ink with one blue accent. Colours come from the tokens in
// app/globals.css and never from a hex code here.

export function Card({ title, action, children, className = '', tone = 'surface' }) {
  const surface = {
    surface: 'bg-[--color-surface] border-[--color-line]',
    accent: 'bg-[--color-accent] border-transparent',
    ink: 'bg-[--color-rail] border-transparent text-white',
  }[tone]

  return (
    <section className={`rounded-[--radius-card] border ${surface} ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className={title || action ? 'px-5 pb-5' : 'p-5'}>{children}</div>
    </section>
  )
}

export function Button({ variant = 'default', className = '', ...props }) {
  const styles = {
    primary: 'bg-[--color-rail] text-white hover:opacity-90',
    default: 'border border-[--color-line] bg-[--color-surface] hover:bg-[--color-sunken]',
    good: 'bg-[--color-good] text-white hover:opacity-90',
    danger: 'border border-[--color-bad] text-[--color-bad] hover:bg-[--color-bad-soft]',
    ghost: 'text-[--color-brand] hover:bg-[--color-brand-soft]',
  }[variant]

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    />
  )
}

const TONES = {
  neutral: 'bg-[--color-sunken] text-[--color-muted] border-[--color-line]',
  brand: 'bg-[--color-brand-soft] text-[--color-accent-deep] border-transparent',
  good: 'bg-[--color-good-soft] text-[--color-good] border-transparent',
  warn: 'bg-[--color-warn-soft] text-[--color-warn] border-transparent',
  bad: 'bg-[--color-bad-soft] text-[--color-bad] border-transparent',
}

export function Badge({ tone = 'neutral', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
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

/** A small rounded tile holding an icon or glyph, as on every card header. */
export function IconChip({ children, tone = 'neutral', className = '' }) {
  const styles = {
    neutral: 'bg-[--color-sunken] text-[--color-muted]',
    brand: 'bg-[--color-brand-soft] text-[--color-accent-deep]',
    ink: 'bg-[--color-rail] text-white',
    plain: 'bg-white/70 text-[--color-ink]',
  }[tone]
  return (
    <span
      aria-hidden="true"
      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[--radius-inner] text-sm ${styles} ${className}`}
    >
      {children}
    </span>
  )
}

/**
 * A percentage ring, the small badge beside a stat's number.
 * Pure CSS conic gradient: no chart library, no SVG to keep in sync.
 */
export function Ring({ value, label }) {
  const pct = Math.max(0, Math.min(100, Math.round(value || 0)))
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white/70 px-2 py-1 text-xs font-medium">
      <span className="tabular">{pct}%</span>
      <span
        role="img"
        aria-label={label ? `${label}: ${pct} percent` : `${pct} percent`}
        className="h-3.5 w-3.5 rounded-full"
        style={{
          background: `conic-gradient(var(--color-ink) ${pct * 3.6}deg, rgba(17,22,28,0.15) 0)`,
        }}
      />
    </span>
  )
}

/**
 * The segmented meter from the reference: filled blocks up to the value, dashed
 * outlines for the remainder. Reads as a quantity even without the number, and
 * the gap between blocks is the 2px surface spacer the mark spec asks for.
 */
export function Bar({ value, max = 100, tone = 'brand', segments = 10, label }) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0
  const filled = Math.round(ratio * segments)
  const fill = {
    brand: 'var(--color-brand)',
    ink: 'var(--color-ink)',
    good: 'var(--color-good)',
    warn: 'var(--color-warn)',
    bad: 'var(--color-bad)',
  }[tone] ?? 'var(--color-brand)'

  return (
    <div
      className="flex items-center gap-1.5"
      role="img"
      aria-label={`${label ? label + ': ' : ''}${Math.round(ratio * 100)} percent`}
    >
      {Array.from({ length: segments }, (_, i) => (
        <span
          key={i}
          className="h-7 flex-1 rounded-[7px] transition-colors"
          style={
            i < filled
              ? { background: fill }
              : { border: '1.5px dashed color-mix(in srgb, var(--color-ink) 18%, transparent)' }
          }
        />
      ))}
    </div>
  )
}

/**
 * A stat tile: icon, label, hero number, optional ring and meter.
 * The hero number is the mark here, so it carries no series colour - ink only.
 */
export function StatCard({ icon, label, value, of, ring, meter, hint, tone = 'surface' }) {
  return (
    <Card tone={tone} className="flex h-full flex-col">
      <div className="flex items-center gap-2">
        <IconChip tone={tone === 'surface' ? 'neutral' : 'plain'}>{icon}</IconChip>
        <span className="text-sm font-medium">{label}</span>
      </div>

      <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="hero-number tabular">{value}</span>
        {of && <span className="text-sm text-[--color-muted] tabular">/ {of}</span>}
        {ring != null && <Ring value={ring} label={label} />}
      </div>

      {meter}
      {hint && <p className="mt-3 text-sm text-[--color-muted]">{hint}</p>}
    </Card>
  )
}

/**
 * The capsule chart from the reference: one rounded column per category with a
 * dot at the value. Two series at most, direct-labelled, so identity never rests
 * on colour alone.
 */
export function CapsuleChart({ items, max, legend }) {
  const ceiling = max || Math.max(1, ...items.map((i) => i.value))
  return (
    <figure className="m-0">
      {legend && (
        <figcaption className="mb-4 flex flex-wrap items-center gap-4 text-xs text-[--color-muted]">
          {legend.map((entry) => (
            <span key={entry.label} className="inline-flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: entry.color }}
                aria-hidden="true"
              />
              {entry.label}
            </span>
          ))}
        </figcaption>
      )}

      <div className="flex items-end gap-3 overflow-x-auto no-scrollbar sm:gap-5">
        {items.map((item) => {
          const height = Math.max(6, Math.round((item.value / ceiling) * 100))
          return (
            <div key={item.label} className="flex min-w-14 flex-1 flex-col items-center gap-2">
              <span className="text-xs font-medium tabular">{item.display ?? item.value}</span>
              <div className="relative flex h-40 w-9 items-end justify-center rounded-full bg-[--color-sunken]">
                <div
                  className="flex w-9 items-start justify-center rounded-full pt-1.5"
                  style={{ height: `${height}%`, background: item.color }}
                >
                  <span
                    className="h-3 w-3 rounded-full bg-white/90"
                    aria-hidden="true"
                  />
                </div>
              </div>
              <span className="text-center text-xs text-[--color-muted]">{item.label}</span>
            </div>
          )
        })}
      </div>
    </figure>
  )
}

export function Table({ columns, rows, renderRow, empty, onRowClick }) {
  if (!rows?.length) return <Empty>{empty}</Empty>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-[--color-muted]">
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
              className={`border-t border-[--color-line] ${
                onRowClick ? 'cursor-pointer hover:bg-[--color-sunken]' : ''
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
  return <td className={`py-3 pr-4 align-middle ${className}`}>{children}</td>
}

export function Empty({ children }) {
  return (
    <p className="rounded-[--radius-inner] bg-[--color-sunken] px-4 py-10 text-center text-sm text-[--color-muted]">
      {children || 'Nothing here yet.'}
    </p>
  )
}

export function Loading({ what = 'Loading' }) {
  return <p className="px-1 py-8 text-sm text-[--color-muted]">{what}…</p>
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="flex items-center justify-between gap-3 rounded-[--radius-inner] bg-[--color-bad-soft] px-4 py-3 text-sm text-[--color-bad]">
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
    <p className="rounded-full bg-[--color-warn-soft] px-3.5 py-1.5 text-xs text-[--color-warn]">
      {children}
    </p>
  )
}

/** The pill row used for filters and sub-navigation, as in the reference. */
export function Pills({ options, value, onChange, ariaLabel = 'Filter' }) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="flex gap-1.5 overflow-x-auto no-scrollbar">
      {options.map((option) => {
        const key = option.value ?? option
        const label = option.label ?? option
        const active = key === value
        return (
          <button
            key={key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(key)}
            className={`whitespace-nowrap rounded-full px-4 py-2 text-sm transition ${
              active
                ? 'bg-[--color-rail] font-medium text-white'
                : 'text-[--color-muted] hover:bg-[--color-sunken]'
            }`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
