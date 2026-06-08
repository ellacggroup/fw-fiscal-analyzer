import { useState } from 'react'
import { FileText, Clock, RefreshCw, Layers, Search, X, ArrowDownUp } from 'lucide-react'
import { reanalyzeAgenda, reanalyzeAll } from '../services/api'

export default function HistorySidebar({ agendas, currentId, onSelect, onReanalyzed }) {
  const [reanalyzing, setReanalyzing] = useState(null)
  const [reanalyzingAll, setReanalyzingAll] = useState(false)
  const [search, setSearch] = useState('')
  const [sortDir, setSortDir] = useState('desc')   // 'desc' = newest first, 'asc' = oldest first

  if (!agendas.length) return null

  const filtered = (search.trim()
    ? agendas.filter(a =>
        (a.filename || '').toLowerCase().includes(search.toLowerCase()) ||
        (a.meeting_date || '').toLowerCase().includes(search.toLowerCase())
      )
    : [...agendas]
  ).sort((a, b) => {
    const da = new Date(a.uploaded_at)
    const db = new Date(b.uploaded_at)
    return sortDir === 'desc' ? db - da : da - db
  })

  async function handleReanalyze(e, uploadId) {
    e.stopPropagation()
    setReanalyzing(uploadId)
    try {
      const result = await reanalyzeAgenda(uploadId)
      if (onReanalyzed) onReanalyzed(result)
    } catch (err) {
      alert('Reanalysis failed: ' + (err.response?.data?.detail || err.message))
    } finally {
      setReanalyzing(null)
    }
  }

  async function handleReanalyzeAll() {
    if (!window.confirm(`Reanalyze all ${agendas.length} agendas? This will refresh the Comprehensive Plan lookup for every zoning item. May take a few minutes.`)) return
    setReanalyzingAll(true)
    try {
      await reanalyzeAll()
      window.location.reload()
    } catch (err) {
      alert('Reanalyze all failed: ' + (err.response?.data?.detail || err.message))
    } finally {
      setReanalyzingAll(false)
    }
  }

  return (
    <aside className="w-64 flex-shrink-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-gray-500">
          Upload History
        </h2>
        <button
          onClick={handleReanalyzeAll}
          disabled={reanalyzingAll}
          title="Refresh Comprehensive Plan data for all agendas"
          className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-40 font-semibold"
        >
          <Layers className={`w-3.5 h-3.5 ${reanalyzingAll ? 'animate-pulse' : ''}`} />
          {reanalyzingAll ? 'Updating…' : 'Refresh All'}
        </button>
      </div>

      {/* Search bar */}
      <div className="relative mb-2">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search agendas…"
          className="w-full pl-8 pr-7 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-fw-blue focus:ring-1 focus:ring-fw-blue placeholder-gray-400"
        />
        {search && (
          <button
            onClick={() => setSearch('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Sort toggle */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-gray-400">{filtered.length} agenda{filtered.length !== 1 ? 's' : ''}</span>
        <button
          onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-fw-blue font-semibold transition-colors"
          title={sortDir === 'desc' ? 'Showing newest first — click for oldest first' : 'Showing oldest first — click for newest first'}
        >
          <ArrowDownUp className="w-3 h-3" />
          {sortDir === 'desc' ? 'Newest first' : 'Oldest first'}
        </button>
      </div>

      <div className="space-y-2">
        {filtered.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">No agendas match "{search}"</p>
        )}
        {filtered.map((a) => (
          <div
            key={a.upload_id}
            onClick={() => onSelect(a.upload_id)}
            className={`w-full text-left rounded-lg border p-3 transition-all hover:shadow-sm cursor-pointer ${
              currentId === a.upload_id
                ? 'border-fw-blue bg-blue-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <div className="flex items-start gap-2">
              <FileText className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-gray-800 truncate">{a.filename}</p>
                <div className="flex items-center gap-1 mt-1">
                  <Clock className="w-3 h-3 text-gray-400" />
                  <span className="text-xs text-gray-400">
                    {new Date(a.uploaded_at).toLocaleDateString()}
                  </span>
                  <span className="ml-auto text-xs text-gray-500">{a.item_count} items</span>
                </div>

                {/* Reanalyze button */}
                <button
                  onClick={(e) => handleReanalyze(e, a.upload_id)}
                  disabled={reanalyzing === a.upload_id}
                  className="mt-2 w-full flex items-center justify-center gap-1.5 text-xs text-indigo-600 border border-indigo-200 rounded-md py-1 hover:bg-indigo-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Re-run analysis with latest engine improvements"
                >
                  <RefreshCw className={`w-3 h-3 ${reanalyzing === a.upload_id ? 'animate-spin' : ''}`} />
                  {reanalyzing === a.upload_id ? 'Reanalyzing…' : 'Reanalyze'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}
