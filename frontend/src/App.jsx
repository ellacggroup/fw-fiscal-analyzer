import { useState, useEffect, useCallback } from 'react'
import { Building2, AlertCircle, FileSpreadsheet, FileDown, Sparkles, Bell, BarChart2, MapPin, Upload } from 'lucide-react'
import UploadZone from './components/UploadZone'
import FiscalCard from './components/FiscalCard'
import HistorySidebar from './components/HistorySidebar'
import SummaryBar from './components/SummaryBar'
import AlertsPanel from './components/AlertsPanel'
import HistoryView from './components/HistoryView'
import CompetitivePanel from './components/CompetitivePanel'
import {
  uploadAndAnalyzeAgenda,
  uploadFromUrl,
  getAgenda,
  listAgendas,
  exportExcelUrl,
  exportPdfUrl,
  uploadStaffReport,
  getUnreadAlertCount,
  getUnreadProximityCount,
} from './services/api'

export default function App() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [agendaHistory, setAgendaHistory] = useState([])
  const [currentAgenda, setCurrentAgenda] = useState(null)
  const [filterRating, setFilterRating] = useState('ALL')
  const [filterCategory, setFilterCategory] = useState('ALL')
  const [mainTab, setMainTab] = useState('agenda')  // 'agenda' | 'alerts' | 'history' | 'competitive'
  const [alertUnread, setAlertUnread] = useState(0)
  const [proximityUnread, setProximityUnread] = useState(0)
  const [staffReportUploading, setStaffReportUploading] = useState(false)
  const [staffReportResult, setStaffReportResult] = useState(null)

  useEffect(() => {
    listAgendas()
      .then(data => {
        const sorted = [...data].sort((a, b) =>
          new Date(b.uploaded_at) - new Date(a.uploaded_at)
        )
        setAgendaHistory(sorted)
      })
      .catch(() => {})
    // Load unread badge counts
    getUnreadAlertCount().then(setAlertUnread).catch(() => {})
    getUnreadProximityCount().then(setProximityUnread).catch(() => {})
  }, [])

  const handleUpload = useCallback(async (file) => {
    setLoading(true)
    setError(null)
    setCurrentAgenda(null)
    try {
      const result = await uploadAndAnalyzeAgenda(file)
      setCurrentAgenda(result)
      const history = await listAgendas()
      setAgendaHistory([...history].sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at)))
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'An error occurred.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleUploadUrl = useCallback(async (url) => {
    setLoading(true)
    setError(null)
    setCurrentAgenda(null)
    try {
      const result = await uploadFromUrl(url)
      setCurrentAgenda(result)
      const history = await listAgendas()
      setAgendaHistory([...history].sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at)))
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'An error occurred.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleSelectHistory = useCallback(async (uploadId) => {
    setError(null)
    try {
      const full = await getAgenda(uploadId)
      setCurrentAgenda(full)
      setFilterRating('ALL')
      setFilterCategory('ALL')
    } catch {
      setError('Could not load agenda.')
    }
  }, [])

  // Build sorted list of categories present in this agenda
  const categories = currentAgenda
    ? ['ALL', ...Array.from(new Set(
        currentAgenda.items.map(i => i.category || 'Other')
      )).sort()]
    : ['ALL']

  const visibleItems = currentAgenda?.items?.filter(item => {
    const ratingMatch = filterRating === 'ALL'
      || (item.analysis?.fiscal_impact_rating || 'UNKNOWN') === filterRating
    const categoryMatch = filterCategory === 'ALL'
      || (item.category || 'Other') === filterCategory
    return ratingMatch && categoryMatch
  }) ?? []

  const claudeEnabled = currentAgenda?.claude_enabled
    || currentAgenda?.items?.some(i => i.analysis?.claude_available)

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-fw-blue text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center gap-3">
          <Building2 className="w-7 h-7 text-fw-gold flex-shrink-0" />
          <div className="flex-1">
            <h1 className="text-lg font-bold leading-tight">Fort Worth Fiscal Impact Analyzer</h1>
            <p className="text-xs text-blue-200">City Council Agenda Analysis · AI-Powered</p>
          </div>
          {/* Navigation tabs */}
          <nav className="flex gap-1">
            {[
              { key: 'agenda',      icon: Building2,  label: 'Agendas',     badge: 0 },
              { key: 'history',     icon: BarChart2,  label: 'History',     badge: 0 },
              { key: 'alerts',      icon: Bell,       label: 'Alerts',      badge: alertUnread },
              { key: 'competitive', icon: MapPin,     label: 'Competitive', badge: proximityUnread },
            ].map(({ key, icon: Icon, label, badge }) => (
              <button key={key} onClick={() => setMainTab(key)}
                className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  mainTab === key ? 'bg-white/20 text-white' : 'text-blue-200 hover:text-white hover:bg-white/10'
                }`}>
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{label}</span>
                {badge > 0 && (
                  <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                    {badge > 9 ? '9+' : badge}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Main layout */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-4 py-6 flex gap-6">

        {/* Sidebar — only shown on agenda tab */}
        {mainTab === 'agenda' && (
          <HistorySidebar
            agendas={agendaHistory}
            currentId={currentAgenda?.upload_id}
            onSelect={handleSelectHistory}
            onReanalyzed={(result) => {
              setCurrentAgenda(result)
              setFilterRating('ALL')
              setFilterCategory('ALL')
            }}
          />
        )}

        <main className="flex-1 min-w-0 space-y-6">

        {/* Non-agenda tabs */}
        {mainTab === 'history' && <HistoryView />}
        {mainTab === 'alerts' && (
          <AlertsPanel onUnreadChange={count => setAlertUnread(count)} />
        )}
        {mainTab === 'competitive' && (
          <CompetitivePanel onUnreadChange={count => setProximityUnread(count)} />
        )}

        {/* Agenda tab content */}
        {mainTab === 'agenda' && (<>
          <UploadZone
            onUpload={handleUpload}
            onUploadUrl={handleUploadUrl}
            loading={loading}
          />

          {error && (
            <div className="flex gap-3 items-start bg-red-50 border border-red-200 rounded-xl p-4 text-red-800">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-sm">Could not process agenda</p>
                <p className="text-sm mt-0.5">{error}</p>
              </div>
            </div>
          )}

          {currentAgenda && (
            <>
              {/* Title + export row */}
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">{currentAgenda.filename}</h2>
                  <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                    {currentAgenda.meeting_date && (
                      <p className="text-sm text-gray-500">Meeting: {currentAgenda.meeting_date}</p>
                    )}
                    {claudeEnabled && (
                      <span className="flex items-center gap-1 text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full font-semibold">
                        <Sparkles className="w-3 h-3" /> Claude AI
                      </span>
                    )}
                  </div>
                </div>

                {/* Export + Staff Report buttons */}
                <div className="flex gap-2 flex-wrap">
                  <a href={exportExcelUrl(currentAgenda.upload_id)} download
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-green-600 text-green-700 hover:bg-green-50 font-semibold transition-colors">
                    <FileSpreadsheet className="w-4 h-4" /> Excel
                  </a>
                  <a href={exportPdfUrl(currentAgenda.upload_id)} download
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-red-600 text-red-700 hover:bg-red-50 font-semibold transition-colors">
                    <FileDown className="w-4 h-4" /> PDF
                  </a>
                  <label className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-blue-600 text-blue-700 hover:bg-blue-50 font-semibold transition-colors cursor-pointer ${staffReportUploading ? 'opacity-50' : ''}`}>
                    <Upload className="w-4 h-4" />
                    {staffReportUploading ? 'Uploading…' : 'M&C Report'}
                    <input type="file" accept=".pdf" className="hidden"
                      disabled={staffReportUploading}
                      onChange={async e => {
                        const file = e.target.files[0]
                        if (!file) return
                        setStaffReportUploading(true)
                        setStaffReportResult(null)
                        try {
                          const result = await uploadStaffReport(currentAgenda.upload_id, file)
                          setStaffReportResult(result)
                          if (result.matched_items > 0) {
                            const refreshed = await getAgenda(currentAgenda.upload_id)
                            setCurrentAgenda(refreshed)
                          }
                        } catch (err) {
                          setStaffReportResult({ error: err.response?.data?.detail || 'Upload failed' })
                        } finally {
                          setStaffReportUploading(false)
                          e.target.value = ''
                        }
                      }} />
                  </label>
                </div>
              </div>

              {/* Staff report result */}
              {staffReportResult && (
                <div className={`rounded-xl border p-3 text-sm flex items-start gap-2 ${
                  staffReportResult.error ? 'bg-red-50 border-red-200 text-red-800' : 'bg-blue-50 border-blue-200 text-blue-800'
                }`}>
                  <Upload className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    {staffReportResult.error
                      ? staffReportResult.error
                      : staffReportResult.matched_items > 0
                        ? `M&C staff report applied to ${staffReportResult.matched_items} item(s). ${staffReportResult.mc_data?.mc_summary || ''}`
                        : `Staff report parsed but no matching items found. ${staffReportResult.mc_data?.mc_summary || ''}`}
                  </div>
                </div>
              )}

              <SummaryBar items={currentAgenda.items} />

              {/* Filters */}
              <div className="space-y-2">
                {/* Rating filter */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-16 flex-shrink-0">Rating</span>
                  {['ALL', 'POSITIVE', 'NEUTRAL', 'NEGATIVE', 'UNKNOWN'].map(r => {
                    const count = r === 'ALL'
                      ? currentAgenda.items.filter(i =>
                          filterCategory === 'ALL' || (i.category || 'Other') === filterCategory
                        ).length
                      : currentAgenda.items.filter(i =>
                          (i.analysis?.fiscal_impact_rating || 'UNKNOWN') === r &&
                          (filterCategory === 'ALL' || (i.category || 'Other') === filterCategory)
                        ).length
                    return (
                      <button
                        key={r}
                        onClick={() => setFilterRating(r)}
                        className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${
                          filterRating === r
                            ? 'bg-fw-blue text-white border-fw-blue'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                        }`}
                      >
                        {r === 'ALL' ? 'All' : r.charAt(0) + r.slice(1).toLowerCase()}
                        <span className="ml-1 opacity-70">({count})</span>
                      </button>
                    )
                  })}
                </div>

                {/* Category filter */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-16 flex-shrink-0">Category</span>
                  {categories.map(cat => {
                    const count = cat === 'ALL'
                      ? currentAgenda.items.filter(i =>
                          filterRating === 'ALL' || (i.analysis?.fiscal_impact_rating || 'UNKNOWN') === filterRating
                        ).length
                      : currentAgenda.items.filter(i =>
                          (i.category || 'Other') === cat &&
                          (filterRating === 'ALL' || (i.analysis?.fiscal_impact_rating || 'UNKNOWN') === filterRating)
                        ).length
                    return (
                      <button
                        key={cat}
                        onClick={() => setFilterCategory(cat)}
                        className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${
                          filterCategory === cat
                            ? 'bg-fw-gold text-white border-fw-gold'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                        }`}
                      >
                        {cat === 'ALL' ? 'All categories' : cat}
                        <span className="ml-1 opacity-70">({count})</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="space-y-3">
                {visibleItems.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-8">No items match this filter.</p>
                ) : (
                  visibleItems.map(item => <FiscalCard key={item.id} item={item} />)
                )}
              </div>

              <div className="text-xs text-gray-400 border-t border-gray-200 pt-4 leading-relaxed">
                <strong>Methodology:</strong> Quantitative estimates use Fort Worth's property tax rate
                ($0.7125/$100 AV) and the Fate TX 40-year revenue-to-cost framework.
                {claudeEnabled
                  ? ' Qualitative summaries, risk ratings, and recurring/one-time flags are generated by Claude AI (claude-sonnet-4-6).'
                  : ' Analysis is rule-based. Add an ANTHROPIC_API_KEY to .env for AI-powered summaries.'}
                {' '}Estimates are for informational purposes only.
              </div>
            </>
          )}

          {!currentAgenda && !loading && !error && (
            <div className="text-center py-12 text-gray-400">
              <Building2 className="w-16 h-16 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Upload a Fort Worth City Council agenda PDF to get started</p>
              <p className="text-xs mt-1 text-gray-300">
                Upload a file or paste a URL · Exports to Excel &amp; PDF
              </p>
            </div>
          )}
        </>)}
        </main>
      </div>
    </div>
  )
}
