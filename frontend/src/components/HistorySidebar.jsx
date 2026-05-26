import { FileText, Clock, ChevronRight } from 'lucide-react'

export default function HistorySidebar({ agendas, currentId, onSelect }) {
  if (!agendas.length) return null

  return (
    <aside className="w-64 flex-shrink-0">
      <h2 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-3">Upload History</h2>
      <div className="space-y-2">
        {agendas.map((a) => (
          <button
            key={a.upload_id}
            onClick={() => onSelect(a.upload_id)}
            className={`w-full text-left rounded-lg border p-3 transition-all hover:shadow-sm ${
              currentId === a.upload_id
                ? 'border-fw-blue bg-blue-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <div className="flex items-start gap-2">
              <FileText className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-gray-800 truncate">{a.filename}</p>
                {a.meeting_date && (
                  <p className="text-xs text-gray-500 mt-0.5">{a.meeting_date}</p>
                )}
                <div className="flex items-center gap-1 mt-1">
                  <Clock className="w-3 h-3 text-gray-400" />
                  <span className="text-xs text-gray-400">
                    {new Date(a.uploaded_at).toLocaleDateString()}
                  </span>
                  <span className="ml-auto text-xs text-gray-500">{a.item_count} items</span>
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </aside>
  )
}
