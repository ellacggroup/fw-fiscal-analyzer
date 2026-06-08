import { useState, useEffect } from 'react'
import { getAnalyticsSummary, getZoningActivity, getTimeline, getIncentiveHistory } from '../services/api'
import { TrendingUp, TrendingDown, Minus, HelpCircle, BarChart2, Map, DollarSign } from 'lucide-react'

const RATING_COLOR = {
  POSITIVE: 'bg-green-500',
  NEUTRAL:  'bg-yellow-400',
  NEGATIVE: 'bg-red-500',
  UNKNOWN:  'bg-gray-300',
}
const RATING_TEXT = {
  POSITIVE: 'text-green-700',
  NEUTRAL:  'text-yellow-700',
  NEGATIVE: 'text-red-700',
  UNKNOWN:  'text-gray-500',
}

function fmt(n) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : '+'
  if (abs >= 1_000_000) return `${sign}$${(abs/1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}$${(abs/1_000).toFixed(0)}K`
  return `${sign}$${abs}`
}

export default function HistoryView() {
  const [tab, setTab]           = useState('summary')
  const [summary, setSummary]   = useState(null)
  const [zoning, setZoning]     = useState([])
  const [timeline, setTimeline] = useState([])
  const [incentives, setIncentives] = useState([])
  const [loading, setLoading]   = useState(false)
  const [districtFilter, setDistrictFilter] = useState('')

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getAnalyticsSummary(),
      getZoningActivity(),
      getTimeline(),
      getIncentiveHistory(),
    ]).then(([s, z, t, i]) => {
      setSummary(s)
      setZoning(z.items || [])
      setTimeline(t)
      setIncentives(i.items || [])
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-sm text-gray-400 text-center py-12">Loading analytics…</div>

  const filteredZoning = districtFilter
    ? zoning.filter(z => z.district === districtFilter)
    : zoning

  const maxTotal = Math.max(...timeline.map(t => t.total || 0), 1)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <BarChart2 className="w-5 h-5 text-fw-blue" />
        <h2 className="text-lg font-bold text-gray-900">Historical Tracking</h2>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200">
        {[
          { key: 'summary',    label: 'Summary' },
          { key: 'zoning',     label: 'Zoning Activity' },
          { key: 'timeline',   label: 'Timeline' },
          { key: 'incentives', label: 'Economic Incentives' },
        ].map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              tab === key ? 'border-fw-blue text-fw-blue' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'summary' && summary && (
        <div className="space-y-6">
          {/* Stat cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Agendas Uploaded', value: summary.total_uploads },
              { label: 'Total Items',       value: summary.total_items },
              { label: 'Earliest Meeting',  value: summary.date_range?.earliest || '—' },
              { label: 'Latest Meeting',    value: summary.date_range?.latest || '—' },
            ].map(s => (
              <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-1">{s.label}</p>
                <p className="text-lg font-black text-gray-900">{s.value}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {/* By category */}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Items by Category</p>
              <div className="space-y-2">
                {Object.entries(summary.by_category || {}).map(([cat, count]) => (
                  <div key={cat} className="flex items-center gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className="text-gray-700 truncate">{cat}</span>
                        <span className="font-bold text-gray-900 ml-2">{count}</span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className="h-full bg-fw-blue rounded-full"
                          style={{ width: `${(count / summary.total_items) * 100}%` }} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* By rating */}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Fiscal Impact Distribution</p>
              <div className="space-y-2">
                {Object.entries(summary.by_rating || {}).map(([rating, count]) => (
                  <div key={rating} className="flex items-center gap-3">
                    <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${RATING_COLOR[rating] || 'bg-gray-300'}`} />
                    <span className="text-xs text-gray-700 flex-1">{rating}</span>
                    <span className="text-xs font-bold text-gray-900">{count}</span>
                    <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${RATING_COLOR[rating] || 'bg-gray-300'}`}
                        style={{ width: `${(count / summary.total_items) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* By district */}
          {Object.keys(summary.by_district || {}).length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Activity by Council District</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.by_district).map(([dist, count]) => (
                  <div key={dist} className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-center">
                    <p className="text-xs font-bold text-fw-blue">CD {dist}</p>
                    <p className="text-lg font-black text-gray-900">{count}</p>
                    <p className="text-xs text-gray-500">items</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'zoning' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <select value={districtFilter} onChange={e => setDistrictFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-fw-blue">
              <option value="">All Districts</option>
              {[...new Set(zoning.map(z => z.district).filter(Boolean))].sort((a,b) => +a - +b).map(d => (
                <option key={d} value={d}>District {d}</option>
              ))}
            </select>
            <span className="text-xs text-gray-500">{filteredZoning.length} zoning cases</span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-xs">
              <thead className="bg-fw-blue text-white">
                <tr>
                  {['Date', 'District', 'Case', 'From → To', 'Acres', 'Comp Plan', 'Rating'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredZoning.length === 0 && (
                  <tr><td colSpan={7} className="text-center text-gray-400 py-6">No zoning cases found</td></tr>
                )}
                {filteredZoning.map((z, i) => (
                  <tr key={z.item_id} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                    <td className="px-3 py-2 whitespace-nowrap">{z.meeting_date || '—'}</td>
                    <td className="px-3 py-2">{z.district ? `CD ${z.district}` : '—'}</td>
                    <td className="px-3 py-2 max-w-[160px] truncate" title={z.title}>{z.title}</td>
                    <td className="px-3 py-2 whitespace-nowrap font-mono">
                      {z.zoning_from || '?'} → {z.zoning_to || '?'}
                    </td>
                    <td className="px-3 py-2">{z.acreage != null ? `${z.acreage} ac` : '—'}</td>
                    <td className="px-3 py-2">
                      {z.consistent === 'Yes'
                        ? <span className="text-green-700 font-semibold">Consistent</span>
                        : z.consistent === 'No'
                          ? <span className="text-red-700 font-semibold">Inconsistent</span>
                          : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`font-semibold ${RATING_TEXT[z.fiscal_impact_rating] || 'text-gray-400'}`}>
                        {z.fiscal_impact_rating || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'timeline' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">Items per agenda by fiscal impact rating</p>
          <div className="space-y-3">
            {timeline.map(row => (
              <div key={row.meeting_date} className="flex items-center gap-3">
                <span className="text-xs text-gray-600 w-32 flex-shrink-0 truncate">{row.meeting_date}</span>
                <div className="flex-1 flex h-5 rounded overflow-hidden gap-0.5">
                  {['POSITIVE','NEUTRAL','NEGATIVE','UNKNOWN'].map(r => {
                    const count = row[r] || 0
                    const width = `${(count / maxTotal) * 100}%`
                    return count > 0 ? (
                      <div key={r} className={`${RATING_COLOR[r]} flex items-center justify-center`}
                        style={{ width }} title={`${r}: ${count}`}>
                        {count > 2 && <span className="text-white text-[10px] font-bold">{count}</span>}
                      </div>
                    ) : null
                  })}
                </div>
                <span className="text-xs text-gray-400 w-10 text-right">{row.total}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-4 flex-wrap">
            {[['POSITIVE','Green'],['NEUTRAL','Yellow'],['NEGATIVE','Red'],['UNKNOWN','Gray']].map(([r, label]) => (
              <div key={r} className="flex items-center gap-1.5">
                <div className={`w-3 h-3 rounded ${RATING_COLOR[r]}`} />
                <span className="text-xs text-gray-600">{label} = {r.charAt(0)+r.slice(1).toLowerCase()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'incentives' && (
        <div className="space-y-3">
          {incentives.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">No economic incentive items found across uploaded agendas.</p>
          )}
          {incentives.map(inc => (
            <div key={inc.item_id} className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
              <div className="flex items-start justify-between gap-2 flex-wrap">
                <div>
                  <p className="text-xs text-gray-500">{inc.meeting_date || '—'}</p>
                  <p className="text-sm font-semibold text-gray-900">{inc.title}</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {inc.incentive_type && (
                    <span className="text-xs bg-emerald-100 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold">
                      {inc.incentive_type}
                    </span>
                  )}
                  {inc.mc_enriched && (
                    <span className="text-xs bg-blue-100 text-blue-800 border border-blue-200 px-2 py-0.5 rounded-full font-semibold">
                      Staff Report Data
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-4 text-xs">
                {inc.mc_investment && (
                  <div>
                    <span className="text-gray-400">Investment: </span>
                    <span className="font-semibold text-gray-800">${inc.mc_investment.toLocaleString()}</span>
                  </div>
                )}
                {inc.min_foregone != null && (
                  <div>
                    <span className="text-gray-400">Min foregone/yr: </span>
                    <span className="font-semibold text-red-700">{fmt(inc.min_foregone)}</span>
                  </div>
                )}
                {inc.term_years && (
                  <div>
                    <span className="text-gray-400">Term: </span>
                    <span className="font-semibold text-gray-800">{inc.term_years} years</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
