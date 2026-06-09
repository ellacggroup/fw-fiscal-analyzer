import axios from 'axios'

const api = axios.create({ baseURL: '' })

export async function uploadAndAnalyzeAgenda(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/agendas/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,   // Claude analysis can take up to ~90 s for a large agenda
  })
  return data
}

export async function uploadFromUrl(url) {
  const { data } = await api.post('/agendas/upload-url', { url }, {
    timeout: 150_000,
  })
  return data
}

export async function getAgenda(uploadId) {
  const { data } = await api.get(`/agendas/${uploadId}`)
  return data
}

export async function listAgendas() {
  const { data } = await api.get('/agendas/')
  return data
}

export async function reanalyzeAgenda(uploadId) {
  const { data } = await api.post(`/agendas/${uploadId}/reanalyze`, {}, {
    timeout: 120_000,
  })
  return data
}

export async function reanalyzeAll() {
  const { data } = await api.post('/agendas/reanalyze-all', {}, {
    timeout: 300_000,
  })
  return data
}

export function exportExcelUrl(uploadId) {
  return `/agendas/${uploadId}/export/excel`
}

export function exportPdfUrl(uploadId) {
  return `/agendas/${uploadId}/export/pdf`
}

// ── Parcel lookup ────────────────────────────────────────────────────────────
export async function lookupParcelsForAgenda(uploadId) {
  const { data } = await api.post(`/parcels/agenda/${uploadId}`, {}, { timeout: 60_000 })
  return data
}
export async function lookupParcelForItem(itemId) {
  const { data } = await api.post(`/parcels/item/${itemId}`, {}, { timeout: 15_000 })
  return data
}
export async function getParcelsForAgenda(uploadId) {
  const { data } = await api.get(`/parcels/agenda/${uploadId}`)
  return data
}

// ── Staff report upload ───────────────────────────────────────────────────────
export async function uploadStaffReport(uploadId, file, itemNumber = '') {
  const form = new FormData()
  form.append('file', file)
  if (itemNumber) form.append('item_number', itemNumber)
  const { data } = await api.post(`/staff-reports/agenda/${uploadId}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30_000,
  })
  return data
}

// ── Alerts ────────────────────────────────────────────────────────────────────
export async function listAlerts() {
  const { data } = await api.get('/alerts/')
  return data
}
export async function createAlert(label, alertType, criteria) {
  const { data } = await api.post('/alerts/', { label, alert_type: alertType, criteria })
  return data
}
export async function deleteAlert(id) {
  const { data } = await api.delete(`/alerts/${id}`)
  return data
}
export async function getAlertMatches(unreadOnly = false) {
  const { data } = await api.get('/alerts/matches', { params: { unread_only: unreadOnly } })
  return data
}
export async function getUnreadAlertCount() {
  const { data } = await api.get('/alerts/matches/unread-count')
  return data.unread || 0
}
export async function markAlertMatchRead(matchId) {
  const { data } = await api.post(`/alerts/matches/${matchId}/read`)
  return data
}
export async function markAllAlertsRead() {
  const { data } = await api.post('/alerts/matches/read-all')
  return data
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export async function getAnalyticsSummary() {
  const { data } = await api.get('/analytics/summary')
  return data
}
export async function getZoningActivity(params = {}) {
  const { data } = await api.get('/analytics/zoning-activity', { params })
  return data
}
export async function getTimeline() {
  const { data } = await api.get('/analytics/timeline')
  return data
}
export async function getIncentiveHistory() {
  const { data } = await api.get('/analytics/economic-incentives')
  return data
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export async function getCategoryTrends() {
  const { data } = await api.get('/analytics/category-trends')
  return data
}
export async function getVotesByMember(category = '') {
  const { data } = await api.get('/analytics/votes-by-member', { params: category ? { category } : {} })
  return data
}
export async function getZoningTransitions() {
  const { data } = await api.get('/analytics/zoning-transitions')
  return data
}
export async function getVotesTimeline() {
  const { data } = await api.get('/analytics/votes-timeline')
  return data
}

// ── Bulk import ───────────────────────────────────────────────────────────────
export async function startBulkImport(years = 5) {
  const { data } = await api.post('/bulk-import/start', { years }, { timeout: 30_000 })
  return data
}
export async function getBulkImportStatus(jobId) {
  const { data } = await api.get(`/bulk-import/status/${jobId}`)
  return data
}
export async function listBulkImportJobs() {
  const { data } = await api.get('/bulk-import/jobs')
  return data
}
export async function reprocessVotes() {
  const { data } = await api.post('/bulk-import/reprocess-votes', {}, { timeout: 30_000 })
  return data
}
export async function syncYouTubeVotes() {
  const { data } = await api.post('/bulk-import/sync-youtube-votes', {}, { timeout: 30_000 })
  return data
}

// ── Competitive intelligence ──────────────────────────────────────────────────
export async function listWatchedProperties() {
  const { data } = await api.get('/competitive/properties')
  return data
}
export async function addWatchedProperty(label, address, radiusMiles = 1.0) {
  const { data } = await api.post('/competitive/properties', { label, address, radius_miles: radiusMiles })
  return data
}
export async function deleteWatchedProperty(id) {
  const { data } = await api.delete(`/competitive/properties/${id}`)
  return data
}
export async function getProximityAlerts(unreadOnly = false) {
  const { data } = await api.get('/competitive/alerts', { params: { unread_only: unreadOnly } })
  return data
}
export async function getUnreadProximityCount() {
  const { data } = await api.get('/competitive/alerts/unread-count')
  return data.unread || 0
}
export async function markProximityAlertRead(alertId) {
  const { data } = await api.post(`/competitive/alerts/${alertId}/read`)
  return data
}
