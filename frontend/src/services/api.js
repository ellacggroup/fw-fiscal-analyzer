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
