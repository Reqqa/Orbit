// Every call to the Orbit backend goes through here.
//
// In development Next.js serves the dashboard on :3000 and the Python API runs on
// :8000, so NEXT_PUBLIC_API_BASE points at the API. In production FastAPI serves the
// exported dashboard itself, the base is empty, and everything is same-origin.
const BASE = (process.env.NEXT_PUBLIC_API_BASE || '').replace(/\/$/, '')

export const apiUrl = (path) => `${BASE}${path}`

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    // 'include' rather than 'same-origin': the signed session cookie has to travel
    // from :3000 to :8000 in development.
    credentials: 'include',
    headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body.detail) detail = body.detail
    } catch {
      // not JSON, keep the status line
    }
    const error = new Error(detail)
    error.status = response.status
    throw error
  }

  if (response.status === 204) return null
  const type = response.headers.get('content-type') || ''
  return type.includes('application/json') ? response.json() : response.text()
}

const json = (body) => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  health: () => request('/api/health'),

  // Session and the demo role switcher
  session: () => request('/api/session'),
  switchableUsers: () => request('/api/session/users'),
  switchUser: (userId) => request('/api/session', json({ user_id: userId })),

  // Approvals
  approvals: (status = 'PENDING') => request(`/api/approvals?status=${encodeURIComponent(status)}`),
  approval: (id) => request(`/api/approvals/${id}`),
  decide: (id, decision, note, edits) =>
    request(`/api/approvals/${id}/decision`, json({ decision, note, edits })),

  // Ledger
  dashboard: () => request('/api/dashboard/summary'),
  invoices: (params = '') => request(`/api/invoices${params}`),
  timeline: (id) => request(`/api/invoices/${id}/timeline`),
  customers: () => request('/api/customers'),
  payments: () => request('/api/payments'),

  // Audit
  audit: (params = '') => request(`/api/audit${params}`),
  verifyAudit: () => request('/api/audit/verify'),
  auditExportUrl: apiUrl('/api/audit/export.jsonl'),

  // Chasing
  chaseBatch: () => request('/api/chasing/batch/tomorrow'),
  chaseRunNow: () => request('/api/chasing/run-now', { method: 'POST' }),
  chaseApprove: (batchDate, reminderIds, skipIds = []) =>
    request(`/api/chasing/batch/${batchDate}/approve`, json({ reminder_ids: reminderIds, skip_ids: skipIds })),

  // Settings
  settings: () => request('/api/settings'),
  saveSettings: (payload) => request('/api/settings', { method: 'PUT', body: JSON.stringify(payload) }),

  // Simulator
  simulatorThread: (customerId) => request(`/api/simulator/thread/${customerId}`),
  simulatorSend: (customerId, file, text) => {
    const form = new FormData()
    form.append('customer_id', customerId)
    if (file) form.append('file', file)
    if (text) form.append('text', text)
    return request('/api/simulator/send', { method: 'POST', body: form })
  },
}

export { request }
