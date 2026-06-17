import { useState, useEffect } from 'react'
import { getZoningActivity } from '../services/api'
import { BarChart2, ArrowRight, TrendingUp, TrendingDown, Minus } from 'lucide-react'

const RATING_DOT = {
  POSITIVE: 'bg-green-500',
  NEUTRAL:  'bg-yellow-400',
  NEGATIVE: 'bg-red-500',
  UNKNOWN:  'bg-gray-300',
}

const BROAD_COLOR = {
  'Residential':        'bg-amber-100 text-amber-800 border-amber-300',
  'Commercial':         'bg-red-100 text-red-800 border-red-300',
  'Industrial':         'bg-slate-100 text-slate-800 border-slate-300',
  'Mixed-Use':          'bg-purple-100 text-purple-800 border-purple-300',
  'Institutional / CF': 'bg-blue-100 text-blue-800 border-blue-300',
  'Agricultural / Open':'bg-lime-100 text-lime-800 border-lime-300',
  'Planned Development':'bg-indigo-100 text-indigo-800 border-indigo-300',
  'Other':              'bg-gray-100 text-gray-600 border-gray-200',
}

const ZONE_BROAD = {
  'A-5':'Residential','A-10':'Residential','A-21':'Residential','A-43':'Residential',
  'AR':'Residential','GR':'Residential','B':'Residential','C':'Residential',
  'D':'Residential','D-HR':'Residential','UR':'Residential','R1':'Residential',
  'AG':'Agricultural / Open','AN':'Agricultural / Open','O-1':'Agricultural / Open',
  'E':'Commercial','ER':'Commercial','F':'Commercial','FR':'Commercial',
  'G':'Commercial','H':'Commercial','NS':'Commercial',
  'I':'Industrial','J':'Industrial','K':'Industrial',
  'CF':'Institutional / CF',
  'MU-1':'Mixed-Use','MU-2':'Mixed-Use','MU':'Mixed-Use',
}

function broadCategory(code) {
  if (!code) return 'Other'
  const clean = code.trim().toUpperCase().split('/')[0]
  if (ZONE_BROAD[clean]) return ZONE_BROAD[clean]
  if (clean.startsWith('PD')) return 'Planned Development'
  if (clean.startsWith('TL-')) return 'Mixed-Use'
  if (clean.startsWith('SY-')) return 'Commercial'
  return 'Other'
}

function Badge({ label }) {
  const cls = BROAD_COLOR[label] || BROAD_COLOR['Other']
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${cls}`}>
      {label}
    </span>
  )
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
  const [tab, setTab]           = useState('transitions')
  const [zoning, setZoning]     = useState([])
  const [loading, setLoading]   = useState(false)
  const [search, setSearch]     = useState('')
  const [filterFrom, setFilterFrom] = useState('')
  const [filterTo, setFilterTo]     = useState('')

  useEffect(() => {
    setLoading(true)
    getZoningActivity()
      .then(z => {
        setZoning(z.items || [])
      })
      .finally(() => setLoading(false))
  }, [])

  // Build transition counts from raw zoning items
  const transitions = {}
  for (const item of zoning) {
    if (!item.zoning_from || !item.zoning_to) continue
    const from = item.zoning_from
    const to   = item.zoning_to
    const key  = `${from}|||${to}`
    const fromBroad = broadCategory(from)
    const toBroad   = broadCategory(to)
    if (!transitions[key]) {
      transitions[key] = {
        from_code: from, to_code: to,
        from_broad: fromBroad, to_broad: toBroad,
        count: 0, total_acres: 0, districts: new Set(), meetings: new Set(),
        items: [],
      }
    }
    transitions[key].count++
    transitions[key].total_acres += item.acreage || 0
    if (item.district) transitions[key].districts.add(item.district)
    if (item.meeting_date) transitions[key].meetings.add(item.meeting_date)
    transitions[key].items.push(item)
  }

  let transitionList = Object.values(transitions)
    .map(t => ({
      ...t,
      districts: [...t.districts].sort((a,b) => +a - +b),
      meetings:  [...t.meetings].sort(),
      total_acres: Math.round(t.total_acres * 100) / 100,
    }))
    .sort((a, b) => b.count - a.count)

  // Filter
  if (filterFrom) transitionList = transitionList.filter(t =>
    t.from_broad === filterFrom || t.from_code.toUpperCase().startsWith(filterFrom.toUpperCase())
  )
  if (filterTo) transitionList = transitionList.filter(t =>
    t.to_broad === filterTo || t.to_code.toUpperCase().startsWith(filterTo.toUpperCase())
  )
  if (search) {
    const s = search.toLowerCase()
    transitionList = transitionList.filter(t =>
      t.from_code.toLowerCase().includes(s) ||
      t.to_code.toLowerCase().includes(s) ||
      t.from_broad.toLowerCase().includes(s) ||
      t.to_broad.toLowerCase().includes(s)
    )
  }

  // Broad category rollup
  const broadRollup = {}
  for (const t of Object.values(transitions)) {
    const key = `${t.from_broad}|||${t.to_broad}`
    if (!broadRollup[key]) {
      broadRollup[key] = { from: t.from_broad, to: t.to_broad, count: 0, acres: 0 }
    }
    broadRollup[key].count += t.count
    broadRollup[key].acres += t.total_acres
  }
  const broadList = Object.values(broadRollup)
    .sort((a, b) => b.count - a.count)
    .map(r => ({ ...r, acres: Math.round(r.acres * 100) / 100 }))

  const allBroads = [...new Set(Object.values(transitions).flatMap(t => [t.from_broad, t.to_broad]))].sort()
  const maxCount = Math.max(...transitionList.map(t => t.count), 1)

  if (loading) return <div className="text-sm text-gray-400 text-center py-12">Loading trends…</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <BarChart2 className="w-5 h-5 text-fw-blue" />
        <div>
          <h2 className="text-lg font-bold text-gray-900">Zoning &amp; Land Use Trends</h2>
          <p className="text-xs text-gray-500">Patterns across all uploaded agendas · {zoning.length} zoning cases</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200">
        {[
          { key: 'transitions', label: 'Transition Patterns' },
          { key: 'broad',       label: 'By Land Use Type' },
          { key: 'cases',       label: 'All ZC Cases' },
        ].map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              tab === key ? 'border-fw-blue text-fw-blue' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Transition Patterns ── */}
      {tab === 'transitions' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">
            How many zoning cases requested each specific code change, sorted by frequency.
          </p>

          {/* Filters */}
          <div className="flex gap-2 flex-wrap items-center">
            <select value={filterFrom} onChange={e => setFilterFrom(e.target.value)}
              className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-fw-blue">
              <option value="">All From types</option>
              {allBroads.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
            <ArrowRight className="w-3.5 h-3.5 text-gray-400" />
            <select value={filterTo} onChange={e => setFilterTo(e.target.value)}
              className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-fw-blue">
              <option value="">All To types</option>
              {allBroads.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search zone codes…"
              className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-fw-blue w-40" />
            {(filterFrom || filterTo || search) && (
              <button onClick={() => { setFilterFrom(''); setFilterTo(''); setSearch('') }}
                className="text-xs text-gray-400 hover:text-gray-600">Clear</button>
            )}
            <span className="text-xs text-gray-400 ml-auto">{transitionList.length} patterns</span>
          </div>

          {transitionList.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">No matching transition patterns.</p>
          )}

          <div className="space-y-2">
            {transitionList.map((t, i) => (
              <div key={i} className="bg-white rounded-xl border border-gray-200 p-4">
                {/* Zone codes + categories */}
                <div className="flex items-center gap-3 flex-wrap mb-3">
                  <div className="text-center">
                    <p className="text-lg font-black font-mono text-gray-800">{t.from_code}</p>
                    <Badge label={t.from_broad} />
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
                  <div className="text-center">
                    <p className="text-lg font-black font-mono text-fw-blue">{t.to_code}</p>
                    <Badge label={t.to_broad} />
                  </div>
                  <div className="ml-auto text-right">
                    <p className="text-2xl font-black text-gray-900">{t.count}</p>
                    <p className="text-xs text-gray-400">case{t.count !== 1 ? 's' : ''}</p>
                  </div>
                </div>

                {/* Bar */}
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-3">
                  <div className="h-full bg-fw-blue rounded-full transition-all"
                    style={{ width: `${(t.count / maxCount) * 100}%` }} />
                </div>

                {/* Stats */}
                <div className="flex flex-wrap gap-4 text-xs text-gray-500">
                  <span><strong className="text-gray-800">{t.total_acres} ac</strong> total acreage</span>
                  {t.districts.length > 0 && (
                    <span>Districts: <strong className="text-gray-800">{t.districts.map(d => `CD ${d}`).join(', ')}</strong></span>
                  )}
                  {t.meetings.length > 0 && (
                    <span>Meetings: <strong className="text-gray-800">{t.meetings.join(' · ')}</strong></span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Broad Land Use Rollup ── */}
      {tab === 'broad' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">
            Zoning changes grouped by broad land use category — shows the overall direction of land use change across all cases.
          </p>

          {broadList.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">No data available.</p>
          )}

          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-fw-blue text-white">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold">From Land Use</th>
                  <th className="px-2 py-3"></th>
                  <th className="px-4 py-3 text-left font-semibold">To Land Use</th>
                  <th className="px-4 py-3 text-right font-semibold">Cases</th>
                  <th className="px-4 py-3 text-right font-semibold">Total Acres</th>
                  <th className="px-4 py-3 text-left font-semibold w-40">Frequency</th>
                </tr>
              </thead>
              <tbody>
                {broadList.map((r, i) => {
                  const same = r.from === r.to
                  return (
                    <tr key={i} className={`border-t border-gray-100 ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                      <td className="px-4 py-3"><Badge label={r.from} /></td>
                      <td className="px-2 py-3">
                        <ArrowRight className={`w-4 h-4 ${same ? 'text-gray-300' : 'text-indigo-400'}`} />
                      </td>
                      <td className="px-4 py-3"><Badge label={r.to} /></td>
                      <td className="px-4 py-3 text-right font-bold text-gray-900">{r.count}</td>
                      <td className="px-4 py-3 text-right text-gray-600">{r.acres} ac</td>
                      <td className="px-4 py-3">
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-fw-blue rounded-full"
                            style={{ width: `${(r.count / broadList[0].count) * 100}%` }} />
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Same-category note */}
          <p className="text-xs text-gray-400">
            Rows where From and To are the same category represent modifications within that use type
            (e.g. adding a CUP, changing density standards, or overlay additions).
          </p>
        </div>
      )}

      {/* ── All ZC Cases ── */}
      {tab === 'cases' && (
        <div className="space-y-4">
          <p className="text-xs text-gray-500">All zoning change cases across uploaded agendas, most recent first.</p>
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-xs">
              <thead className="bg-fw-blue text-white">
                <tr>
                  {['Date', 'CD', 'Case / Title', 'From', 'To', 'Acres', 'Comp Plan', 'Rating'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {zoning.length === 0 && (
                  <tr><td colSpan={8} className="text-center text-gray-400 py-6">No zoning cases found</td></tr>
                )}
                {zoning.map((z, i) => (
                  <tr key={z.item_id} className={`border-t border-gray-100 ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                    <td className="px-3 py-2 whitespace-nowrap text-gray-600">{z.meeting_date || '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{z.district ? `CD ${z.district}` : '—'}</td>
                    <td className="px-3 py-2 max-w-[200px] truncate text-gray-800" title={z.title}>{z.title}</td>
                    <td className="px-3 py-2">
                      <span className="font-mono font-bold text-gray-700">{z.zoning_from || '—'}</span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="font-mono font-bold text-fw-blue">{z.zoning_to || '—'}</span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{z.acreage != null ? `${z.acreage}` : '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {z.consistent === 'Yes'
                        ? <span className="text-green-700 font-semibold">✓ Consistent</span>
                        : z.consistent === 'No'
                          ? <span className="text-red-700 font-semibold">✗ Inconsistent</span>
                          : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`font-semibold ${
                        z.fiscal_impact_rating === 'POSITIVE' ? 'text-green-700' :
                        z.fiscal_impact_rating === 'NEGATIVE' ? 'text-red-700' :
                        z.fiscal_impact_rating === 'NEUTRAL'  ? 'text-yellow-700' : 'text-gray-400'
                      }`}>{z.fiscal_impact_rating || '—'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  )
}
