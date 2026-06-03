import { useState } from 'react'
import { FileText, Clock, RefreshCw, Layers } from 'lucide-react'
import { reanalyzeAgenda, reanalyzeAll } from '../services/api'

export default function HistorySidebar({ agendas, currentId, onSelect, onReanalyzed }) {
  const [reanalyzing, setReanalyzing] = useState(null)
  const [reanalyzingAll, setReanalyzingAll] = useState(false)

  if (!agendas.length) return null

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
      <div className="space-y-2">
        {agendas.map((a) => (
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
