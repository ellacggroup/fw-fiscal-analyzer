import { useState, useEffect } from 'react'
import { TrendingUp, Users, BarChart2, FileText, Filter, Clock, Download, X, ChevronLeft } from 'lucide-react'
import {
  getCategoryTrends, getVotesByMember, getAnalyticsSummary,
  getZoningActivity, getIncentiveHistory, getMemberVoteItems,
} from '../services/api'
import HistoryView from './HistoryView'
import BulkImportPanel from './BulkImportPanel'

const CATEGORY_COLORS = {
  // Core development approvals
  'Zoning Change':                 '#2563eb',
  'Site Plan / Plat':              '#7c3aed',
  'Platting':                      '#db2777',
  'Land Use / Comp Plan':          '#0891b2',
  // Financial tools
  'Economic Incentive':            '#16a34a',
  'Development Agreement':         '#15803d',
  'TIRZ / Tax Increment':          '#065f46',
  'Public Improvement District':   '#0d9488',
  'Impact / Development Fees':     '#d97706',
  // Property & infrastructure
  'Annexation':                    '#dc2626',
  'Right-of-Way / Easement':       '#9a3412',
  'Land Acquisition / Disposition':'#78350f',
  'Utility Extension / Infrastructure': '#1d4ed8',
  // Regulatory
  'Development Code / Standards':  '#64748b',
}


function pct(n, total) {
  if (!total) return 0
  return Math.round((n / total) * 100)
}

// ── Mini bar chart using plain divs ──────────────────────────────────────────
function BarChart({ data, categories }) {
  if (!data || data.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">No data yet. Run a bulk import first.</p>
  }

  const maxVal = Math.max(...data.map(d => d.total || 0), 1)

  return (
    <div className="space-y-2">
      {/* Legend */}
      <div className="flex flex-wrap gap-3 mb-3">
        {categories.map(cat => (
          <span key={cat} className="flex items-center gap-1.5 text-xs text-gray-600">
            <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat] || '#94a3b8' }} />
            {cat}
          </span>
        ))}
      </div>

      {/* Bars */}
      <div className="overflow-x-auto">
        <div style={{ minWidth: `${Math.max(data.length * 56, 400)}px` }}>
          {/* Stacked bars */}
          <div className="flex items-end gap-1 h-40">
            {data.map(row => {
              const total = row.total || 0
              const heightPx = total ? Math.max(4, Math.round((total / maxVal) * 152)) : 0
              return (
                <div key={row.quarter} className="flex-1 flex flex-col items-center gap-1 group relative">
                  {/* Tooltip */}
                  <div className="absolute bottom-full mb-2 bg-gray-900 text-white text-xs rounded-lg px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
                    <p className="font-bold mb-1">{row.quarter}</p>
                    {categories.map(cat => row[cat] > 0 && (
                      <p key={cat}>{cat}: {row[cat]}</p>
                    ))}
                    <p className="border-t border-gray-700 mt-1 pt-1">Total: {total}</p>
                  </div>

                  {/* Stacked bar segments */}
                  <div
                    className="w-full flex flex-col-reverse rounded-t overflow-hidden"
                    style={{ height: `${heightPx}px` }}
                  >
                    {categories.map(cat => {
                      const val = row[cat] || 0
                      if (!val) return null
                      const segHeight = (val / total) * heightPx
                      return (
                        <div
                          key={cat}
                          style={{
                            height: `${segHeight}px`,
                            backgroundColor: CATEGORY_COLORS[cat] || '#94a3b8',
                            flexShrink: 0,
                          }}
                        />
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          {/* X-axis labels */}
          <div className="flex gap-1 mt-1">
            {data.map(row => (
              <div key={row.quarter} className="flex-1 text-center">
                <span className="text-[10px] text-gray-400 block truncate">
                  {row.quarter.replace('-', '\n')}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Council votes — self-contained panel with drill-down ─────────────────────
// All sub-components defined at module level (never nested) to avoid React
// treating them as new component types on each render, which breaks onClick.

const VOTE_COLORS = {
  AYE:     { pill: 'bg-green-100 text-green-700 border-green-200', text: 'text-green-700' },
  NAY:     { pill: 'bg-red-100 text-red-700 border-red-200',       text: 'text-red-600'   },
  ABSTAIN: { pill: 'bg-yellow-100 text-yellow-700 border-yellow-200', text: 'text-yellow-600' },
  ABSENT:  { pill: 'bg-gray-100 text-gray-500 border-gray-200',    text: 'text-gray-400'  },
}
const VOTE_LABEL = { AYE: 'Aye', NAY: 'Nay', ABSTAIN: 'Abstain', ABSENT: 'Absent' }

function AgendaItemRow({ item, showVoteBadge }) {
  const pillCls = (VOTE_COLORS[item.vote] || {}).pill || ''
  return (
    <div className="px-5 py-3.5 hover:bg-gray-50">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {showVoteBadge && item.vote && (
              <span className={`text-xs px-1.5 py-0.5 rounded border font-semibold flex-shrink-0 ${pillCls}`}>
                {VOTE_LABEL[item.vote] || item.vote}
              </span>
            )}
            <p className="text-sm font-medium text-gray-900 leading-snug">{item.title || '(no title)'}</p>
          </div>
          {item.summary && item.summary !== item.title && (
            <p className="text-xs text-gray-500 mt-1 leading-relaxed">{item.summary}</p>
          )}
        </div>
        {item.fiscal_rating && (
          <span className={`text-xs px-2 py-0.5 rounded-full font-semibold flex-shrink-0 ${
            item.fiscal_rating === 'POSITIVE' ? 'bg-green-100 text-green-700' :
            item.fiscal_rating === 'NEGATIVE' ? 'bg-red-100 text-red-700' :
            'bg-gray-100 text-gray-600'
          }`}>{item.fiscal_rating}</span>
        )}
      </div>
      <div className="flex gap-3 mt-1.5 text-xs text-gray-400 flex-wrap">
        {item.meeting_date && <span>{item.meeting_date}</span>}
        {item.item_number && <span className="font-mono">{item.item_number}</span>}
        {item.category && <span className="text-blue-500">{item.category}</span>}
      </div>
    </div>
  )
}

function DrillBackHeader({ onBack, title, subtitle }) {
  return (
    <div className="px-5 py-3.5 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="text-gray-400 hover:text-gray-700 p-0.5">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div>
          <p className="font-semibold text-gray-900">{title}</p>
          {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      <button onClick={onBack} className="text-gray-400 hover:text-gray-700">
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

// Click a vote count number → see those specific items
function VoteCountDrillDown({ member, voteType, category, onBack }) {
  const [items, setItems] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getMemberVoteItems(member.name, voteType, category)
      .then(d => setItems(d.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [member.name, voteType, category])

  const voteLabel = { AYE: 'Ayes', NAY: 'Nays', ABSTAIN: 'Abstentions', ABSENT: 'Absences' }[voteType] || voteType
  const pillCls = (VOTE_COLORS[voteType] || {}).pill || ''

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <DrillBackHeader
        onBack={onBack}
        title={<>{member.name} <span className={`ml-2 text-xs px-2 py-0.5 rounded-full border font-semibold ${pillCls}`}>{voteLabel}</span></>}
        subtitle={`District ${member.district} · ${category || 'All categories'}${!loading && items ? ` · ${items.length} items` : ''}`}
      />
      <div className="divide-y divide-gray-100 max-h-[540px] overflow-y-auto">
        {loading && <p className="text-sm text-gray-400 text-center py-10">Loading…</p>}
        {!loading && items?.length === 0 && <p className="text-sm text-gray-400 text-center py-10">No items found.</p>}
        {!loading && items?.map(item => (
          <AgendaItemRow key={item.item_id} item={item} showVoteBadge={false} />
        ))}
      </div>
    </div>
  )
}

// Click a member name → see all their votes grouped by category
function MemberVoteProfile({ member, category, onBack }) {
  const [allItems, setAllItems] = useState(null)
  const [loading, setLoading] = useState(true)
  const [voteFilter, setVoteFilter] = useState('')

  useEffect(() => {
    setLoading(true)
    getMemberVoteItems(member.name, '', category)
      .then(d => setAllItems(d.items || []))
      .catch(() => setAllItems([]))
      .finally(() => setLoading(false))
  }, [member.name, category])

  const shown = voteFilter ? (allItems || []).filter(i => i.vote === voteFilter) : (allItems || [])

  const totals = {}
  for (const i of (allItems || [])) totals[i.vote] = (totals[i.vote] || 0) + 1

  const byCat = {}
  for (const i of shown) {
    const c = i.category || 'Other'
    ;(byCat[c] = byCat[c] || []).push(i)
  }
  const sortedCats = Object.keys(byCat).sort()

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <DrillBackHeader
        onBack={onBack}
        title={`${member.name} — All Votes`}
        subtitle={`District ${member.district} · ${category || 'All categories'}${!loading && allItems ? ` · ${shown.length} items` : ''}`}
      />

      {!loading && allItems && allItems.length > 0 && (
        <div className="px-5 py-2.5 border-b border-gray-100 flex gap-2 flex-wrap items-center">
          <span className="text-xs text-gray-500 font-medium">Filter:</span>
          <button
            onClick={() => setVoteFilter('')}
            className={`text-xs px-2.5 py-1 rounded-full border font-semibold ${!voteFilter ? 'bg-gray-800 text-white border-gray-800' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'}`}
          >
            All ({allItems.length})
          </button>
          {['AYE', 'NAY', 'ABSTAIN', 'ABSENT'].filter(v => totals[v]).map(v => (
            <button
              key={v}
              onClick={() => setVoteFilter(voteFilter === v ? '' : v)}
              className={`text-xs px-2.5 py-1 rounded-full border font-semibold ${voteFilter === v ? (VOTE_COLORS[v]?.pill || '') : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'}`}
            >
              {VOTE_LABEL[v]} ({totals[v]})
            </button>
          ))}
        </div>
      )}

      <div className="max-h-[540px] overflow-y-auto">
        {loading && <p className="text-sm text-gray-400 text-center py-10">Loading…</p>}
        {!loading && shown.length === 0 && <p className="text-sm text-gray-400 text-center py-10">No items found.</p>}
        {!loading && sortedCats.map(cat => (
          <div key={cat}>
            <div className="px-5 py-2 bg-gray-50 border-y border-gray-100 flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{cat}</span>
              <span className="text-xs text-gray-400">{byCat[cat].length} item{byCat[cat].length !== 1 ? 's' : ''}</span>
            </div>
            <div className="divide-y divide-gray-100">
              {byCat[cat].map(item => (
                <AgendaItemRow key={item.item_id} item={item} showVoteBadge={!voteFilter} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// The main votes panel — table + drill-down state all in one place
function CouncilVotesPanel({ members, loading, voteCategory, categories, onCategoryChange }) {
  // view: 'table' | 'profile' | 'count'
  const [view, setView] = useState('table')
  const [selectedMember, setSelectedMember] = useState(null)
  const [selectedVoteType, setSelectedVoteType] = useState(null)

  function openProfile(member) {
    setSelectedMember(member)
    setView('profile')
  }

  function openCountDrill(member, voteType) {
    setSelectedMember(member)
    setSelectedVoteType(voteType)
    setView('count')
  }

  function backToTable() {
    setView('table')
    setSelectedMember(null)
    setSelectedVoteType(null)
  }

  if (view === 'profile' && selectedMember) {
    return <MemberVoteProfile member={selectedMember} category={voteCategory} onBack={backToTable} />
  }

  if (view === 'count' && selectedMember && selectedVoteType) {
    return <VoteCountDrillDown member={selectedMember} voteType={selectedVoteType} category={voteCategory} onBack={backToTable} />
  }

  // Table view
  if (loading) return <p className="text-sm text-gray-400 py-6 text-center">Loading votes…</p>
  if (!members || members.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 text-sm">
        <Users className="w-10 h-10 mx-auto mb-2 opacity-30" />
        <p>No vote records found.</p>
        <p className="text-xs mt-1">Vote data is extracted from meeting minutes during bulk import.</p>
      </div>
    )
  }

  return (
    <>
      {/* Category filter */}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <span className="text-sm font-medium text-gray-600 flex items-center gap-1.5">
          <Filter className="w-4 h-4" /> Filter:
        </span>
        <button
          onClick={() => onCategoryChange('')}
          className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${!voteCategory ? 'bg-fw-blue text-white border-fw-blue' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'}`}
        >
          All categories
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => onCategoryChange(cat)}
            className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${voteCategory === cat ? 'bg-fw-blue text-white border-fw-blue' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'}`}
          >
            {cat}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">
            Vote Breakdown by Councilmember
            {voteCategory && <span className="text-gray-400 font-normal"> — {voteCategory}</span>}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">Click a name to see all votes · click a count to see those specific items</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2.5 text-left">Dist.</th>
                <th className="px-4 py-2.5 text-left">Councilmember</th>
                <th className="px-4 py-2.5 text-right">Ayes</th>
                <th className="px-4 py-2.5 text-right">Nays</th>
                <th className="px-4 py-2.5 text-right">Abstain</th>
                <th className="px-4 py-2.5 text-right">Absent</th>
                <th className="px-4 py-2.5 text-left min-w-28">Aye Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {members.map(m => {
                const total = (m.AYE || 0) + (m.NAY || 0) + (m.ABSTAIN || 0) + (m.ABSENT || 0)
                const ayePct = pct(m.AYE || 0, total - (m.ABSENT || 0))
                return (
                  <tr key={`${m.name}|${m.district}`} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-fw-blue text-white text-xs font-bold">
                        {m.district || '?'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        type="button"
                        onClick={() => openProfile(m)}
                        className="font-medium text-blue-600 underline underline-offset-2 hover:text-blue-800 text-left cursor-pointer"
                      >
                        {m.name}
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {m.AYE > 0
                        ? <button type="button" onClick={() => openCountDrill(m, 'AYE')} className="font-semibold text-green-700 underline underline-offset-2 hover:text-green-900 cursor-pointer tabular-nums">{m.AYE}</button>
                        : <span className="text-gray-300 tabular-nums">0</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {m.NAY > 0
                        ? <button type="button" onClick={() => openCountDrill(m, 'NAY')} className="font-semibold text-red-600 underline underline-offset-2 hover:text-red-800 cursor-pointer tabular-nums">{m.NAY}</button>
                        : <span className="text-gray-300 tabular-nums">0</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {m.ABSTAIN > 0
                        ? <button type="button" onClick={() => openCountDrill(m, 'ABSTAIN')} className="font-semibold text-yellow-600 underline underline-offset-2 hover:text-yellow-800 cursor-pointer tabular-nums">{m.ABSTAIN}</button>
                        : <span className="text-gray-300 tabular-nums">0</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {m.ABSENT > 0
                        ? <button type="button" onClick={() => openCountDrill(m, 'ABSENT')} className="font-semibold text-gray-500 underline underline-offset-2 hover:text-gray-700 cursor-pointer tabular-nums">{m.ABSENT}</button>
                        : <span className="text-gray-300 tabular-nums">0</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-100 rounded-full h-2 min-w-16">
                          <div className="bg-green-500 rounded-full h-2" style={{ width: `${ayePct}%` }} />
                        </div>
                        <span className="text-xs text-gray-500 w-8 text-right tabular-nums">{ayePct}%</span>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

// ── Summary stat cards ────────────────────────────────────────────────────────
function StatCard({ label, value, sub }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-sm font-medium text-gray-600 mt-0.5">{label}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

// ── Zoning activity list ──────────────────────────────────────────────────────
function ZoningList({ items }) {
  const [search, setSearch] = useState('')
  const filtered = items.filter(i =>
    !search || (i.title + ' ' + (i.district || '')).toLowerCase().includes(search.toLowerCase())
  )

  if (items.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">No zoning cases imported yet.</p>
  }

  return (
    <div className="space-y-3">
      <input
        type="text"
        placeholder="Search cases, addresses, districts…"
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
        value={search}
        onChange={e => setSearch(e.target.value)}
      />
      <div className="text-xs text-gray-400">{filtered.length} case{filtered.length !== 1 ? 's' : ''}</div>
      <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
        {filtered.map(item => (
          <div key={item.item_id} className="bg-white rounded-lg border border-gray-100 p-3">
            <div className="flex items-start gap-2 justify-between">
              <p className="text-sm font-medium text-gray-900 flex-1">{item.title}</p>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold flex-shrink-0 ${
                item.fiscal_impact_rating === 'POSITIVE' ? 'bg-green-100 text-green-700' :
                item.fiscal_impact_rating === 'NEGATIVE' ? 'bg-red-100 text-red-700' :
                'bg-gray-100 text-gray-600'
              }`}>{item.fiscal_impact_rating || '—'}</span>
            </div>
            <div className="flex gap-3 mt-1 text-xs text-gray-400 flex-wrap">
              {item.meeting_date && <span>{item.meeting_date}</span>}
              {item.district && <span>District {item.district}</span>}
              {item.zoning_from && item.zoning_to && (
                <span>{item.zoning_from} → {item.zoning_to}</span>
              )}
              {item.acreage && <span>{item.acreage} acres</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function TrendsView() {
  const [tab, setTab] = useState('overview')
  const [trendsData, setTrendsData] = useState(null)
  const [votesData, setVotesData] = useState(null)
  const [summary, setSummary] = useState(null)
  const [zoning, setZoning] = useState([])
  const [incentives, setIncentives] = useState([])
  const [loading, setLoading] = useState(true)
  const [voteCategory, setVoteCategory] = useState('')

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getCategoryTrends(),
      getVotesByMember(),
      getAnalyticsSummary(),
      getZoningActivity(),
      getIncentiveHistory(),
    ])
      .then(([trends, votes, sum, zon, inc]) => {
        setTrendsData(trends)
        setVotesData(votes)
        setSummary(sum)
        setZoning(zon.items || [])
        setIncentives(inc.items || [])
      })
      .finally(() => setLoading(false))
  }, [])

  async function loadVotesForCategory(cat) {
    setVoteCategory(cat)
    try {
      const data = await getVotesByMember(cat)
      setVotesData(data)
    } catch {}
  }

  const categories = trendsData?.categories || []
  const trendRows = trendsData?.by_quarter || []

  // Compute category totals
  const catTotals = {}
  for (const row of trendRows) {
    for (const cat of categories) {
      catTotals[cat] = (catTotals[cat] || 0) + (row[cat] || 0)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">5-Year Trend Analysis</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Zoning, incentives, land use, platting, site plans, and fee actions
          </p>
        </div>
        <TrendingUp className="w-8 h-8 text-fw-blue" />
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="Total Meetings"
            value={summary.total_uploads}
            sub="in database"
          />
          <StatCard
            label="Total Items"
            value={summary.total_items}
            sub="all categories"
          />
          <StatCard
            label="Zoning Cases"
            value={catTotals['Zoning Change'] || 0}
            sub="5-year total"
          />
          <StatCard
            label="Incentive Deals"
            value={(catTotals['Economic Incentive'] || 0) + (catTotals['Development Agreement'] || 0)}
            sub="Chapter 380 + agreements"
          />
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0 -mb-px">
          {[
            { key: 'overview',   label: 'Category Trends', icon: BarChart2  },
            { key: 'votes',      label: 'Council Votes',   icon: Users      },
            { key: 'zoning',     label: 'Zoning Cases',    icon: FileText   },
            { key: 'incentives', label: 'Incentives',      icon: TrendingUp },
            { key: 'history',    label: 'History',         icon: Clock      },
            { key: 'import',     label: 'Import',          icon: Download   },
          ].map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors ${
                tab === key
                  ? 'border-fw-blue text-fw-blue'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Items per Quarter by Category</h3>
            {loading ? (
              <p className="text-sm text-gray-400">Loading trends…</p>
            ) : (
              <BarChart data={trendRows} categories={categories} />
            )}
          </div>

          {/* Category breakdown cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {categories.map(cat => (
              <div
                key={cat}
                className="bg-white rounded-xl border border-gray-200 p-4 cursor-pointer hover:border-blue-400 transition-colors"
                onClick={() => { setTab('votes'); loadVotesForCategory(cat) }}
              >
                <div
                  className="w-3 h-3 rounded-sm mb-2"
                  style={{ backgroundColor: CATEGORY_COLORS[cat] || '#94a3b8' }}
                />
                <p className="text-xl font-bold text-gray-900">{catTotals[cat] || 0}</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-snug">{cat}</p>
                <p className="text-xs text-blue-500 mt-1">View votes →</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'votes' && (
        <div className="space-y-4">
          <CouncilVotesPanel
            members={votesData?.members}
            loading={loading && !votesData}
            voteCategory={voteCategory}
            categories={categories}
            onCategoryChange={loadVotesForCategory}
          />
        </div>
      )}

      {tab === 'zoning' && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Zoning Cases (5-Year)</h3>
          <ZoningList items={zoning} />
        </div>
      )}

      {tab === 'incentives' && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3.5 border-b border-gray-100">
            <h3 className="font-semibold text-gray-800">Economic Incentives (5-Year)</h3>
          </div>
          {incentives.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No incentive deals imported yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                  <th className="px-4 py-2.5 text-left">Date</th>
                  <th className="px-4 py-2.5 text-left">Title</th>
                  <th className="px-4 py-2.5 text-right">Rating</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {incentives.slice(0, 50).map(item => (
                  <tr key={item.item_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap text-xs">{item.meeting_date}</td>
                    <td className="px-4 py-2.5 text-gray-800">{item.title}</td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                        item.rating === 'POSITIVE' ? 'bg-green-100 text-green-700' :
                        item.rating === 'NEGATIVE' ? 'bg-red-100 text-red-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>{item.rating || '—'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'history' && <HistoryView />}
      {tab === 'import' && <BulkImportPanel />}
    </div>
  )
}
