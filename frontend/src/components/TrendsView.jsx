import { useState, useEffect } from 'react'
import { TrendingUp, Users, BarChart2, FileText, Filter } from 'lucide-react'
import {
  getCategoryTrends, getVotesByMember, getAnalyticsSummary,
  getZoningActivity, getIncentiveHistory,
} from '../services/api'

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

const VOTE_COLORS = {
  AYE:     'bg-green-500',
  NAY:     'bg-red-500',
  ABSTAIN: 'bg-yellow-400',
  ABSENT:  'bg-gray-300',
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

// ── Vote breakdown table ──────────────────────────────────────────────────────
function VotesTable({ members, loading }) {
  if (loading) return <p className="text-sm text-gray-400">Loading votes…</p>
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
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-2.5 text-left">District</th>
            <th className="px-4 py-2.5 text-left">Councilmember</th>
            <th className="px-4 py-2.5 text-right">Ayes</th>
            <th className="px-4 py-2.5 text-right">Nays</th>
            <th className="px-4 py-2.5 text-right">Abstain</th>
            <th className="px-4 py-2.5 text-right">Absent</th>
            <th className="px-4 py-2.5 text-right">Total</th>
            <th className="px-4 py-2.5 text-left min-w-32">Aye Rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {members.map(m => {
            const total = (m.AYE || 0) + (m.NAY || 0) + (m.ABSTAIN || 0) + (m.ABSENT || 0)
            const ayePct = pct(m.AYE || 0, total - (m.ABSENT || 0))  // exclude absents from aye rate
            return (
              <tr key={`${m.name}-${m.district}`} className="hover:bg-gray-50">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-fw-blue text-white text-xs font-bold">
                    {m.district || '?'}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-medium text-gray-900">{m.name}</td>
                <td className="px-4 py-2.5 text-right text-green-700 font-semibold">{m.AYE || 0}</td>
                <td className="px-4 py-2.5 text-right text-red-600">{m.NAY || 0}</td>
                <td className="px-4 py-2.5 text-right text-yellow-600">{m.ABSTAIN || 0}</td>
                <td className="px-4 py-2.5 text-right text-gray-400">{m.ABSENT || 0}</td>
                <td className="px-4 py-2.5 text-right text-gray-500">{total}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-100 rounded-full h-2 min-w-16">
                      <div
                        className="bg-green-500 rounded-full h-2"
                        style={{ width: `${ayePct}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 w-8 text-right">{ayePct}%</span>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
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
            { key: 'overview',   label: 'Category Trends', icon: BarChart2 },
            { key: 'votes',      label: 'Council Votes',   icon: Users     },
            { key: 'zoning',     label: 'Zoning Cases',    icon: FileText  },
            { key: 'incentives', label: 'Incentives',      icon: TrendingUp},
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
          {/* Category filter for votes */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-medium text-gray-600 flex items-center gap-1.5">
              <Filter className="w-4 h-4" /> Filter by category:
            </span>
            <button
              onClick={() => loadVotesForCategory('')}
              className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${
                !voteCategory ? 'bg-fw-blue text-white border-fw-blue' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
              }`}
            >
              All categories
            </button>
            {categories.map(cat => (
              <button
                key={cat}
                onClick={() => loadVotesForCategory(cat)}
                className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${
                  voteCategory === cat ? 'bg-fw-blue text-white border-fw-blue' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between">
              <h3 className="font-semibold text-gray-800">
                Vote Breakdown by Councilmember
                {voteCategory && <span className="text-gray-400 font-normal"> — {voteCategory}</span>}
              </h3>
              {votesData && (
                <span className="text-xs text-gray-400">
                  {votesData.total_items_with_votes} items with vote records
                </span>
              )}
            </div>
            <VotesTable members={votesData?.members} loading={loading && !votesData} />
          </div>

          {(!votesData || votesData.total_items_with_votes === 0) && !loading && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-sm text-yellow-800">
              <p className="font-semibold">No vote data found</p>
              <p className="mt-1">Vote records are extracted from meeting minutes. Run a bulk import (Import tab) to populate vote data.</p>
            </div>
          )}
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
    </div>
  )
}
