import { useState, useEffect } from 'react'
import { TrendingUp, BarChart2, FileText, Clock, Download, BookOpen } from 'lucide-react'
import {
  getCategoryTrends, getAnalyticsSummary,
  getZoningActivity,
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
  const [summary, setSummary] = useState(null)
  const [zoning, setZoning] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getCategoryTrends(),
      getAnalyticsSummary(),
      getZoningActivity(),
    ])
      .then(([trends, sum, zon]) => {
        setTrendsData(trends)
        setSummary(sum)
        setZoning(zon.items || [])
      })
      .finally(() => setLoading(false))
  }, [])

const HIDDEN_CATEGORIES = new Set([
    'Contract / Procurement', 'Budget Amendment', 'Personnel', 'Administrative', 'Other',
  ])
  const categories = (trendsData?.categories || []).filter(c => !HIDDEN_CATEGORIES.has(c))
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
            Commercial &amp; real estate development agenda items — Fort Worth City Council
          </p>
        </div>
        <TrendingUp className="w-8 h-8 text-fw-blue" />
      </div>

      {/* Scope disclaimer */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex gap-3 items-start">
        <span className="text-amber-500 text-lg leading-none mt-0.5">⚠</span>
        <div className="text-sm text-amber-800">
          <span className="font-semibold">Development items only.</span> This tool tracks Fort Worth City Council agenda items related to commercial and real estate development — including zoning changes, site plans, platting, land use amendments, development agreements, TIRZ districts, annexations, right-of-way actions, impact fees, and utility extensions. It does <span className="font-semibold">not</span> capture all city council business. Non-development items such as budget amendments, personnel actions, contracts, and policy resolutions are excluded.
        </div>
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
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
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0 -mb-px">
          {[
            { key: 'overview',     label: 'Category Trends', icon: BarChart2  },
            { key: 'zoning',       label: 'Zoning Cases',    icon: FileText   },
            { key: 'history',      label: 'History',         icon: Clock      },
            { key: 'import',       label: 'Import',          icon: Download   },
            { key: 'methodology',  label: 'Methodology',     icon: BookOpen   },
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
                className="bg-white rounded-xl border border-gray-200 p-4"
              >
                <div
                  className="w-3 h-3 rounded-sm mb-2"
                  style={{ backgroundColor: CATEGORY_COLORS[cat] || '#94a3b8' }}
                />
                <p className="text-xl font-bold text-gray-900">{catTotals[cat] || 0}</p>
                <p className="text-xs text-gray-500 mt-0.5 leading-snug">{cat}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'zoning' && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Zoning Cases (5-Year)</h3>
          <ZoningList items={zoning} />
        </div>
      )}


{tab === 'history' && <HistoryView />}
      {tab === 'import' && <BulkImportPanel />}
      {tab === 'methodology' && <MethodologyPanel />}
    </div>
  )
}


// ── Methodology Panel ─────────────────────────────────────────────────────────
function MethodologyPanel() {
  const [open, setOpen] = useState(null)
  const sections = [
    {
      id: 'data-sources',
      title: 'Data Sources & Agenda Import',
      color: 'blue',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>Where agendas come from:</strong> All Fort Worth City Council agendas and meeting minutes are pulled from the City's official legislative management system, <a href="https://fortworthgov.legistar.com" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">fortworthgov.legistar.com</a> (Granicus Legistar), via the public Legistar REST API. This is the same system the City Clerk uses to publish official meeting records.</p>
          <p><strong>What gets imported:</strong> The bulk import (Trends → Import) fetches the meeting list for the configured number of years, downloads each agenda PDF and meeting minutes PDF directly from Legistar, and stores them in the application database. The earliest meeting currently in the database is <strong>May 18, 2021</strong>.</p>
          <p><strong>Daily automatic updates:</strong> A separate scheduled job checks Legistar once a day and automatically imports any newly published agenda — no manual click required. Meetings already in the database are skipped, so this only ever adds new meetings as the City publishes them.</p>
          <p><strong>What gets filtered in:</strong> Not every agenda item is tracked. The app filters for items related to commercial and real estate development using keyword scoring against item titles and descriptions. Non-development items (budget amendments, personnel actions, proclamations, contracts for city services) are excluded. The disclaimer banner on the Agendas tab and Trends tab reflects this.</p>
          <p><strong>Item categories captured:</strong> Zoning Change · Site Plan / Plat · Platting · Annexation · Land Use / Comp Plan · Development Agreement · Economic Incentive · TIRZ / Tax Increment · Public Improvement District · Impact / Development Fees · Right-of-Way / Easement · Land Acquisition / Disposition · Utility Extension / Infrastructure · Development Code / Standards.</p>
          <p><strong>Manual upload:</strong> Individual agendas can also be uploaded directly as PDFs on the Agendas tab. The app extracts text using pdfplumber (a Python PDF library) and runs the same analysis pipeline.</p>
          <p><strong>Limitations:</strong> Scanned/image-based PDFs cannot be parsed. Legistar may not have minutes published for very recent meetings (minutes are typically posted 2–4 weeks after the meeting date). Missing minutes are logged under Trends → Import.</p>
        </div>
      ),
    },
    {
      id: 'fiscal-analysis',
      title: 'Fiscal Impact Analysis — How Ratings Are Calculated',
      color: 'green',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What the fiscal analysis does:</strong> For each development agenda item, the app estimates whether the proposed action is expected to be financially positive, neutral, or negative for the City of Fort Worth's General Fund over time. It uses a rule-based engine — no machine learning — with parameters derived from publicly available Fort Worth fiscal data.</p>

          <p><strong>Ratings:</strong></p>
          <ul className="list-disc pl-5 space-y-1">
            <li><span className="font-semibold text-green-700">POSITIVE</span> — The proposed use is estimated to generate more revenue than it costs the city to serve (revenue-to-cost ratio ≥ 1.0, the value of <code>PARAMETERS.rc_ratio_target</code> in <code>fiscal_analyzer.py</code>).</li>
            <li><span className="font-semibold text-yellow-700">NEUTRAL</span> — Revenue and costs are roughly balanced (R/C ratio 0.85–1.0), or the item is procedural with no direct fiscal impact.</li>
            <li><span className="font-semibold text-red-700">NEGATIVE</span> — The proposed use is estimated to cost more to serve than it generates in revenue (R/C ratio below 0.85). For incentive deals (tax abatements, TIRZ, Chapter 380 agreements), see the "but for" methodology below — the app does not treat every incentive as automatically negative.</li>
            <li><span className="font-semibold text-gray-500">UNKNOWN</span> — The item type does not permit a revenue/cost estimate from the agenda text alone (e.g., administrative resolutions, appointments).</li>
          </ul>

          <p><strong>Confidence levels:</strong></p>
          <ul className="list-disc pl-5 space-y-1">
            <li><span className="font-semibold">HIGH</span> — A Finance Director certification was found in the M&C staff report (the city's own fiscal officer has certified the impact), or the item type is definitively non-fiscal (procedural hearing).</li>
            <li><span className="font-semibold">MEDIUM</span> — Dollar amounts or acreage were found in the agenda text and used in the estimate.</li>
            <li><span className="font-semibold">LOW</span> — No dollar amount or acreage found; estimate uses default prototype assumptions for the land use type only.</li>
          </ul>

          <p><strong>Finance Director certification:</strong> Fort Worth M&C staff reports often include a section where the Director of Finance certifies whether the item has a positive, negative, or neutral impact on the General Fund. When this language is detected in uploaded staff reports, it overrides the rule-based estimate and the confidence is set to HIGH. This is the most authoritative fiscal statement in the app.</p>

          <p><strong>Category classification:</strong> Each item is classified into a development category by scoring keyword matches against the item title and description. The category with the highest keyword score wins. For example, an item containing "rezone," "zoning change," or "ZC-" is classified as Zoning Change. Items with "TIRZ," "tax increment reinvestment zone" are classified as TIRZ / Tax Increment (board appointments to TIRZ boards are excluded). The full keyword list is defined in <code>backend/services/fiscal_analyzer.py</code>.</p>
        </div>
      ),
    },
    {
      id: 'incentives',
      title: 'Economic Incentives & the "But For" Adjustment',
      color: 'emerald',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>The problem with a simple foregone-revenue calculation:</strong> A tax abatement, TIRZ, or Chapter 380 deal reduces what the city collects compared to the property's full assessed value — but comparing against that full value overstates the cost, because most incentive deals exist specifically because the development would not happen at all without them. If a parcel is vacant or underused today, the real question isn't "how much did the city give up versus the maximum," it's "how much better off is the city than it is right now, doing nothing."</p>

          <p><strong>How the adjustment works:</strong> For every tax abatement, Chapter 380 agreement, or TIRZ item, the app first computes a conservative minimum-foregone-revenue estimate the same way it always has (see Ratings above). Then, if an address can be resolved for the item — either from the City's zoning/comp-plan GIS lookup or extracted directly from the item title — the app queries the <strong>Tarrant Appraisal District (TAD)</strong> for that parcel's <em>current</em> assessed value, and uses the tax on that current value as the real "do nothing" baseline instead of the hypothetical full post-development ceiling.</p>

          <p><strong>Re-rating logic:</strong> The app compares what the city is actually projected to collect during the incentive period against that current-baseline tax:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>If the city nets <strong>more</strong> than the current baseline, the item is rated <span className="font-semibold text-green-700">POSITIVE</span> when the agenda text contains an explicit "but for" finding (see below), or <span className="font-semibold text-yellow-700">NEUTRAL</span> otherwise.</li>
            <li>If the city nets <strong>less</strong> than the current baseline — a genuine loss even accounting for the counterfactual — the item stays <span className="font-semibold text-red-700">NEGATIVE</span>.</li>
          </ul>

          <p><strong>"But for" finding detection:</strong> Texas incentive law (Local Government Code Ch. 380/381, Tax Code Ch. 312) requires the city to find that a project would not occur without the incentive before approving it, so staff reports for these deals usually state this in writing (e.g., "but for this incentive, the applicant would not undertake this project in Fort Worth"). The app scans the agenda text for this language. When present, confidence is set to HIGH and it supports a POSITIVE rating; when absent, confidence is MEDIUM and the narrative flags that the M&C staff report should be checked for the required finding.</p>

          <p><strong>When this doesn't apply:</strong> If no address can be resolved, or TAD has no record for the parcel, the app falls back to the original conservative estimate — it never guesses at a baseline value. Both the "foregone versus ceiling" and "net gain versus current baseline" figures are shown in the item's narrative when the adjustment runs, so nothing is hidden either way.</p>
        </div>
      ),
    },
    {
      id: 'land-use-prototypes',
      title: 'Land Use Prototypes & Revenue-to-Cost Ratios',
      color: 'purple',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What a prototype is:</strong> A land use prototype is a per-acre estimate of how much annual revenue a given development type generates for the city and how much it costs the city to provide services to it. These are used when the agenda text identifies a land use type but no specific dollar amounts are stated.</p>

          <p><strong>Methodology source:</strong> The prototype values are adapted from the <em>Fate, Texas Forward Fate Comprehensive Plan (2021)</em> fiscal impact tool, which provides per-zoning-case revenue-to-cost analysis. Fate's methodology was selected because it is one of the few publicly available Texas municipal fiscal impact frameworks that publishes per-land-use-type revenue and cost estimates. Fort Worth and the City of Dallas do not publish comparable standalone fiscal impact methodology documents. Fort Worth's Comprehensive Plan Appendix F (annexation framework) and the Charlotte, NC 2040 Plan (Economic & Planning Systems scenario-based methodology) were also referenced for structure. The property tax rate used is Fort Worth's actual adopted rate of <strong>$0.7125 per $100 of assessed value</strong> (FY2026 adopted budget).</p>

          <div className="overflow-x-auto">
            <table className="w-full text-xs border border-gray-200 rounded mt-2">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-3 py-2 font-semibold">Land Use Type</th>
                  <th className="text-right px-3 py-2 font-semibold">Revenue/Acre Yr 1</th>
                  <th className="text-right px-3 py-2 font-semibold">Cost/Acre Yr 1</th>
                  <th className="text-right px-3 py-2 font-semibold">R/C Ratio</th>
                  <th className="text-left px-3 py-2 font-semibold">Interpretation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[
                  ['Single-Family Residential', '$2,100', '$2,900', '0.72', 'City spends $1.39 for every $1 collected — police, fire, parks, roads'],
                  ['Multifamily Residential',   '$3,800', '$3,900', '0.97', 'Near break-even; higher density offsets cost per acre'],
                  ['Commercial Retail',         '$14,000','$5,200', '2.70', 'Sales tax + property tax far exceed service cost'],
                  ['Office / Business Park',    '$9,500', '$4,200', '2.26', 'Low service demand, strong property tax base'],
                  ['Industrial / Warehouse',    '$6,500', '$2,800', '2.32', 'Low service demand; no residential costs'],
                  ['Mixed-Use',                 '$8,000', '$4,600', '1.74', 'Blend of residential cost and commercial revenue'],
                  ['Public / Institutional',    '$200',   '$3,000', '0.07', 'Tax-exempt under Texas law; minimal city revenue'],
                  ['Open Space / Park',         '$50',    '$1,800', '0.03', 'No tax revenue; maintenance cost only'],
                ].map(([type, rev, cost, rc, note]) => (
                  <tr key={type} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium">{type}</td>
                    <td className="px-3 py-2 text-right text-green-700">{rev}</td>
                    <td className="px-3 py-2 text-right text-red-600">{cost}</td>
                    <td className={`px-3 py-2 text-right font-bold ${parseFloat(rc) >= 1 ? 'text-green-700' : 'text-red-600'}`}>{rc}</td>
                    <td className="px-3 py-2 text-gray-500">{note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p><strong>Important caveat:</strong> These are prototype estimates, not appraisals. Actual assessed values, actual service costs, and actual development density will differ. The prototypes represent average conditions for Fort Worth-scale municipalities. Individual projects may significantly outperform or underperform these averages depending on property value, build-out rate, and the specific services required.</p>
        </div>
      ),
    },
    {
      id: 'service-cost-breakdown',
      title: 'Supplementary Itemized Cost Estimate',
      color: 'cyan',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What this is:</strong> Every zoning or development-agreement item with a land-use type and acreage now shows a second, independent cost estimate alongside the official rating — built bottom-up from Fort Worth's per-resident and per-lane-mile service cost assumptions instead of the flat per-acre prototype table above. It appears as a collapsible "Supplementary itemized cost estimate" section on each item.</p>

          <p><strong>How it's calculated:</strong> Each land-use type already carries an assumed population, lane-mile, and parkland-acreage density per acre (used elsewhere for infrastructure notes). The itemized estimate multiplies that density by acreage, then applies Fort Worth's per-capita/per-unit cost assumptions: $350/resident for police, $180/resident for fire and EMS, $800 per lane-mile for public works, $12,000 per acre for parks, plus 15% administrative overhead on top.</p>

          <p><strong>Revenue side:</strong> For residential land uses only, a unit count is backed out of the estimated population (÷ 2.4, an average household size), then multiplied by Fort Worth's average assessed value for that unit type ($280,000 single-family, $140,000 multifamily) and the city's actual property tax rate (0.7125%). Commercial, office, and industrial uses don't get an itemized revenue figure — deriving a square footage from acreage alone would require inventing a floor-area-ratio assumption not backed by real data, so it's left blank rather than guessed.</p>

          <p><strong>Why two methodologies instead of one:</strong> The flat per-acre prototype table and this itemized model can disagree significantly — in testing, commercial retail came out roughly 98% <em>lower</em> cost under the itemized model (near-zero population means near-zero police/fire demand), while multifamily came out roughly 255% <em>higher</em> (higher population density drives real per-resident service costs the flat table doesn't fully capture). That's expected: they're measuring cost two different ways, not one being "more correct." The rating itself is still set entirely by the flat per-acre table — this section is a transparency and cross-check tool, not a replacement.</p>

          <p><strong>Limitations:</strong> The density assumptions (population/lane-miles/parks-acreage per acre) are the same fixed per-land-use-type figures used throughout the app, not specific to any individual project's actual density. Neither number is a substitute for an actual staff-report fiscal analysis.</p>
        </div>
      ),
    },
    {
      id: '40yr-projection',
      title: '40-Year NPV Projection',
      color: 'orange',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>Why 40 years:</strong> The 40-year horizon matches the Fate TX fiscal impact methodology and is consistent with long-range municipal capital planning. Development decisions (zoning, platting, annexation) commit the city to providing services for decades — a single-year snapshot understates the true fiscal commitment.</p>

          <p><strong>How it's calculated:</strong> Starting from Year 1 revenue and cost estimates (derived from the land use prototype × acreage, or from dollar amounts in the agenda text), the model projects forward 40 years using:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>Annual growth rate: 2.5%</strong> — applied to both revenue and costs each year. Represents a conservative estimate of assessed value appreciation and service cost inflation for the Fort Worth metro area.</li>
            <li><strong>Discount rate: 3.0%</strong> — used to compute net present value (NPV). Approximates the long-term real return on municipal bonds / opportunity cost of city capital.</li>
            <li><strong>Formula:</strong> Each year's net = (revenue × 1.025^(yr-1)) − (cost × 1.025^(yr-1)). NPV = sum of (net_yr / 1.03^yr) for yr = 1 to 40.</li>
          </ul>
          <p><strong>Break-even year:</strong> The year when cumulative undiscounted net turns positive (total revenue received exceeds total costs incurred). For land uses with R/C &lt; 1, this may never occur within 40 years.</p>
          <p><strong>What it does not include:</strong> One-time infrastructure capital costs (roads, water/sewer extensions), school district impacts, county tax impacts, or state revenue sharing. These can substantially change the true fiscal picture for large annexations or developments.</p>
        </div>
      ),
    },
    {
      id: 'zoning',
      title: 'Zoning Case Analysis',
      color: 'indigo',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>How zoning cases are parsed:</strong> For items classified as Zoning Change (ZC- case numbers), the app extracts the From/To zoning designation using pattern matching against Fort Worth's standard agenda format: <code>From: "A-43" One-Family … To: "E" Neighborhood Commercial</code>. Five fallback patterns handle variations including bare codes (no quotes), PD amendments, informal phrasing ("rezone from … to …"), and dual-designation requests.</p>

          <p><strong>Zone code lookup:</strong> Fort Worth uses a lettered zoning code system (A, A-5, A-43, B, C, D, E, F, G, H, I, J, K, CF, O-1, PD, MU-1, MU-2, etc.) plus special overlay districts (SY-TSA, SY-HCO, PI-UL-2, TL-N). Each code is mapped to a plain-English label and a land use prototype for fiscal analysis. The full code-to-prototype mapping is defined in <code>fiscal_analyzer.py → _FW_ZONE_MAP</code> and <code>_FW_ZONE_TO_PROTOTYPE</code>.</p>

          <p><strong>GIS fallback when text parsing fails:</strong> If none of the five regex patterns can extract a From/To zoning designation from the agenda text, the app queries the City's own <strong>Zoning MapServer</strong> (<code>mapit.fortworthtexas.gov/.../Planning_Development/Zoning/MapServer</code>) directly by case number, checking layers for current/pending cases and the 2023–2025 case archives in order. This is the authoritative city GIS record, not a text guess — when it hits, it also fills in acreage, the applicant name, the requested action, and whether the case is flagged consistent with the Comprehensive Plan, none of which are reliably present in the agenda PDF text itself.</p>

          <p><strong>Incremental analysis:</strong> For zoning changes, the fiscal estimate is the <em>change</em> from current zoning to proposed zoning, not the absolute revenue of the proposed use. A rezoning from Commercial to Single-Family is rated NEGATIVE even though single-family generates positive tax revenue, because it replaces a higher-value use.</p>

          <p><strong>Vacancy assessment:</strong> The app scans the description for signals of current parcel condition ("vacant lot," "undeveloped," "existing building") to indicate whether the parcel is likely vacant or occupied. This affects how realistic the build-out scenario is.</p>

          <p><strong>Zoning Cases tab:</strong> The Zoning Cases sub-tab in Trends shows all ZC- items in the database with their From/To designations, council district, and fiscal direction. Data comes from the same imported agenda items — the tab is a filtered view of the full item table.</p>

          <p><strong>By-right scenarios:</strong> For each proposed zone code, the app also shows what uses are permitted by-right (without additional approval) under that code, based on Fort Worth's Unified Development Code land use tables.</p>
        </div>
      ),
    },
    {
      id: 'trends',
      title: 'Category Trends & Historical Data',
      color: 'teal',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What the trend charts show:</strong> The Category Trends tab charts the volume of development-related agenda items by category per quarter, based on all meetings imported into the database. The time range reflects whatever has been imported (typically 5 years by default).</p>
          <p><strong>Data source:</strong> All trend data is computed from the imported agenda items stored in the local SQLite database. No external data sources are queried for trend analysis — it is entirely derived from the Legistar-imported agenda PDFs.</p>
          <p><strong>Summary statistics (top of Trends page):</strong></p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>Total Meetings</strong> — count of distinct meeting records in the database (unique dates with at least one imported agenda).</li>
            <li><strong>Total Items</strong> — count of all development-related agenda items across all imported meetings.</li>
            <li><strong>Zoning Cases</strong> — count of items classified as Zoning Change (ZC- items) in the 5-year window.</li>
          </ul>
          <p><strong>History sub-tab:</strong> Shows zoning activity grouped by year and category — a rolled-up view of the same imported items, useful for identifying multi-year patterns in development types.</p>
          <p><strong>Categories excluded from Trends:</strong> Contract / Procurement, Budget Amendment, Personnel, Administrative, and Other are filtered out. Only the 14 development-related categories listed under Data Sources are shown.</p>
        </div>
      ),
    },
    {
      id: 'alerts',
      title: 'Watch Alerts & Proximity Alerts',
      color: 'amber',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>Watch Alerts — how matching works:</strong> Each saved alert is one of three types, checked against every new item's title + description at import/upload time:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>District</strong> — the digits in your saved criteria (e.g. "5" from "District 5") are matched against the text using the patterns <code>cd\s*5</code>, <code>district\s+5</code>, and <code>council\s+district\s+5</code>, so "CD5," "CD 5," and "Council District 5" all match.</li>
            <li><strong>Address</strong> — a plain case-insensitive substring match: your saved address text must appear literally somewhere in the item's title/description, or in the address the Comp Plan GIS lookup found for that item (<code>comp_plan_address</code>). A partial or misspelled address will not match.</li>
            <li><strong>Category</strong> — a substring match against the item's assigned category (e.g. "TIRZ" matches "TIRZ / Tax Increment").</li>
          </ul>
          <p>Matches are deduplicated per alert + item pair and stored as <code>AlertMatch</code> records, which is what populates the Alerts tab badge count.</p>

          <p><strong>Proximity Alerts (Competitive tab) — how candidates are chosen:</strong> Not every item is checked against your watched properties, only ones likely to be a real competitive signal: items categorized as <strong>Economic Incentive</strong> or <strong>Development Agreement</strong>, plus <strong>Zoning Change</strong> items estimated at <strong>5 acres or more</strong>. Smaller/routine items are skipped to avoid noise.</p>
          <p><strong>Geocoding:</strong> Both your watched-property address and the candidate item's address (pulled from the Comp Plan GIS address if available, otherwise extracted from the item title with a street-suffix regex — St/Ave/Rd/Dr/Blvd/Ln/Way/Trail/Pkwy/Hwy) are geocoded using the <strong>free U.S. Census Bureau geocoder</strong> (no API key), with an in-process cache so the same address isn't re-queried. If the structured street/city/state query returns no match, it retries once as a single freeform address string.</p>
          <p><strong>Distance calculation:</strong> Straight-line ("as the crow flies," not driving distance) using the <strong>Haversine formula</strong> on the two geocoded lat/lng points. If that distance is ≤ your saved radius (in miles), a <code>ProximityAlert</code> is created, tagged with the deal type (economic incentive type if known, otherwise the item's category) and the exact distance rounded to two decimals.</p>
          <p><strong>Parcel data source (TAD):</strong> When an address is available, the app queries the <strong>Tarrant Appraisal District</strong>'s property search API for owner name, account number, assessed value, and land/improvement value breakdown. If TAD's API doesn't return a match, it falls back to <strong>Tarrant County's public GIS parcel layer</strong> (ArcGIS REST, <code>gis.tarrantcountytx.gov</code>) and searches by matching the first and last words of the address against the parcel's situs address field. Both are official Tarrant County sources; this is supplemental context and only appears when an address could be resolved.</p>
        </div>
      ),
    },
    {
      id: 'comp-plan',
      title: 'Comprehensive Plan Alignment',
      color: 'slate',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What Comp Plan alignment means:</strong> The Fort Worth Comprehensive Plan (adopted 2023) includes a Future Land Use Map (FLUM) that designates intended long-term uses for all land in the city. When a zoning change or land use amendment is proposed, the app attempts to compare the proposed zoning against the FLUM designation for that location.</p>
          <p><strong>Lookup order (fastest/most-authoritative first):</strong></p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>1. Zoning case GIS lookup</strong> — if the item has a ZC/SUP case number, the app queries the same Fort Worth Zoning MapServer used for the Zoning Cases tab. The case record's <code>FUTURE_LAN</code> field gives the Future Land Use code directly, and its <code>CONSISTENC</code> field states whether the City's own system already flags the case as consistent with the Comprehensive Plan — no geocoding needed, and this is the authoritative source when it's available.</li>
            <li><strong>2. Geocode + Future Land Use layer</strong> — if there's no case number or the GIS record has no usable land-use code, the app extracts a street address or intersection from the item text, geocodes it, and queries the City's <strong>Future Land Use MapServer</strong> layer at that point. Because a geocoded point can land in a gap between mapped polygons (common for large or oddly-shaped parcels), the query retries at 19 small offsets in an expanding ring (±0.005° up to ±0.02°, roughly 500m–2km) around the original point before giving up.</li>
          </ul>
          <p><strong>Map link:</strong> Every result includes a link to the City's public Comprehensive Plan ArcGIS web app, centered on the resolved coordinates when geocoding succeeded, so the underlying FLUM designation can be visually verified.</p>
          <p><strong>Limitations:</strong> Comp Plan alignment only appears when a case number resolves in city GIS, or a parcel address can be geocoded and matched to the FLUM layer even after the offset search. Items without a specific address (text amendments, citywide policy items) will not have Comp Plan data. The FLUM is a policy guide, not a legal requirement — the City Council can approve zoning changes that are inconsistent with the FLUM and simultaneously amend the plan.</p>
        </div>
      ),
    },
    {
      id: 'mc-report',
      title: 'M&C Staff Report Upload — Deal-Term Extraction',
      color: 'cyan',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What this is:</strong> On the Agendas tab, the "M&C Report" button lets you upload the full Mayor and Council Communication (M&C) staff report PDF for an item — a separate, more detailed document than the agenda item text itself. It's parsed with the same <code>pdfplumber</code> extraction used for agendas, then scanned with a dedicated set of regex extractors for economic-incentive deal terms.</p>
          <p><strong>Fields extracted, and how:</strong></p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>M&C file number</strong> — pattern <code>M&C (FILE NUMBER:) NN-NNNN</code> from the report header.</li>
            <li><strong>Total investment</strong> — first tries explicit phrasing ("total development costs of $X," "minimum total development costs of $X," "investment of at least $X"); if none match, falls back to the <em>largest</em> dollar figure found within 80 characters of the words "cost," "invest," "construction," or "development."</li>
            <li><strong>Abatement %</strong> — phrasing like "75% tax abatement" or "abatement of 75 percent."</li>
            <li><strong>Chapter 380 rebate %</strong> — phrasing like "85% of new incremental city ad valorem taxes."</li>
            <li><strong>Rebate/grant cap</strong> — phrasing like "not to exceed $80,000,000" or "program cap of $X."</li>
            <li><strong>Incentive term</strong> — phrasing like "15-year term" or "10-year tax abatement."</li>
            <li><strong>Jobs committed</strong> — phrasing like "create at least 200 full-time jobs."</li>
          </ul>
          <p>All dollar figures normalize "million"/"M" and "billion"/"B" suffixes to full numbers. Any field the regex can't find is simply left blank rather than guessed — the summary line shown after upload lists only the terms that were actually detected.</p>
          <p><strong>Relationship to the fiscal rating:</strong> This is separate from the <strong>Finance Director certification</strong> check described above (which looks for the Director of Finance's own stated impact conclusion and can override the rating). Deal-term extraction adds factual detail — dollar amounts, term length, job counts — to Economic Incentive and Development Agreement items; it does not itself change the POSITIVE/NEUTRAL/NEGATIVE rating.</p>
          <p><strong>Limitations:</strong> Regex-based extraction depends on the report using Fort Worth's typical phrasing. Non-standard wording, scanned/image PDFs, or deal terms described only in a referenced exhibit (not the report body) will not be captured.</p>
        </div>
      ),
    },
    {
      id: 'exports',
      title: 'Excel & PDF Export — What\'s in the File',
      color: 'rose',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>What exports contain:</strong> Both the Excel (.xlsx, via <code>openpyxl</code>) and PDF (via <code>reportlab</code>) exports are generated on demand from the exact same stored analysis data shown on screen — nothing is recalculated or re-derived at export time. Excel includes a Summary sheet (filename, meeting date, item counts by rating, whether Claude AI was used) plus a full Agenda Items sheet with one row per item (category, title, rating, risk level, recurring flag, Year-1 net, 40-year net, R/C ratio, Claude summary, key concerns, and methodology notes), color-coded by rating exactly as it appears in the app. The PDF is a condensed, printable version: a summary table plus a per-item table with rating, risk, and a truncated AI/rule-based summary, followed by the same one-line methodology disclaimer shown on the Agendas tab.</p>
          <p><strong>Why this matters:</strong> If you edit an item's data by re-uploading a corrected agenda, re-running analysis, or attaching an M&C staff report, export the file again — a previously downloaded export is a snapshot and will not update itself.</p>
        </div>
      ),
    },
    {
      id: 'ai-analysis',
      title: 'AI-Assisted Analysis (Claude)',
      color: 'violet',
      content: (
        <div className="space-y-4 text-sm text-gray-700">
          <p><strong>When AI is used:</strong> If an Anthropic API key is configured in the backend environment, agenda items are also sent to <strong>Claude (claude-sonnet-4-6)</strong> for qualitative analysis. The AI badge (✦ Claude AI) appears on agenda items that received AI analysis.</p>
          <p><strong>What the AI adds:</strong> Claude provides: a plain-English summary of the item, a risk level assessment (LOW / MEDIUM / HIGH), a flag for whether the fiscal impact is recurring or one-time, key concerns for stakeholders, and in some cases an override of the rule-based fiscal rating when the AI has higher confidence in a different rating.</p>
          <p><strong>What the AI does not do:</strong> The AI does not have access to the internet, Legistar, or any external data source at analysis time. It works only from the agenda item text provided to it. It cannot look up property records, verify zoning maps, or access the actual M&C staff report (unless that report was uploaded separately).</p>
          <p><strong>Rule-based vs. AI ratings:</strong> The rule-based engine runs first and always produces a rating. If Claude is available and produces a non-UNKNOWN rating, Claude's rating takes precedence for POSITIVE/NEGATIVE/NEUTRAL — except for zoning cases and items with a Finance Director certification, where the rule-based incremental analysis or the certified rating is used instead.</p>
          <p><strong>Without an API key:</strong> The app falls back to rule-based analysis only. All fiscal ratings, estimates, and narratives described in this document are still produced — the AI layer adds qualitative commentary on top of the quantitative engine, it does not replace it.</p>
        </div>
      ),
    },
  ]

  const colorMap = {
    blue:   { bg: 'bg-blue-50',   border: 'border-blue-200',  head: 'bg-blue-100',  title: 'text-blue-900',  dot: 'bg-blue-500'   },
    green:  { bg: 'bg-green-50',  border: 'border-green-200', head: 'bg-green-100', title: 'text-green-900', dot: 'bg-green-500'  },
    purple: { bg: 'bg-purple-50', border: 'border-purple-200',head: 'bg-purple-100',title: 'text-purple-900',dot: 'bg-purple-500' },
    orange: { bg: 'bg-orange-50', border: 'border-orange-200',head: 'bg-orange-100',title: 'text-orange-900',dot: 'bg-orange-500' },
    indigo: { bg: 'bg-indigo-50', border: 'border-indigo-200',head: 'bg-indigo-100',title: 'text-indigo-900',dot: 'bg-indigo-500' },
    red:    { bg: 'bg-red-50',    border: 'border-red-200',   head: 'bg-red-100',   title: 'text-red-900',   dot: 'bg-red-500'    },
    teal:   { bg: 'bg-teal-50',   border: 'border-teal-200',  head: 'bg-teal-100',  title: 'text-teal-900',  dot: 'bg-teal-500'   },
    amber:  { bg: 'bg-amber-50',  border: 'border-amber-200', head: 'bg-amber-100', title: 'text-amber-900', dot: 'bg-amber-500'  },
    slate:  { bg: 'bg-slate-50',  border: 'border-slate-200', head: 'bg-slate-100', title: 'text-slate-900', dot: 'bg-slate-500'  },
    violet: { bg: 'bg-violet-50', border: 'border-violet-200',head: 'bg-violet-100',title: 'text-violet-900',dot: 'bg-violet-500' },
    cyan:   { bg: 'bg-cyan-50',   border: 'border-cyan-200',  head: 'bg-cyan-100',  title: 'text-cyan-900',  dot: 'bg-cyan-500'   },
    rose:   { bg: 'bg-rose-50',   border: 'border-rose-200',  head: 'bg-rose-100',  title: 'text-rose-900',  dot: 'bg-rose-500'   },
    emerald:{ bg: 'bg-emerald-50',border: 'border-emerald-200',head: 'bg-emerald-100',title: 'text-emerald-900',dot: 'bg-emerald-500'},
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Methodology & Data Sources</h2>
        <p className="text-sm text-gray-500 mt-0.5">How every number, rating, and data point in this application is derived. Click any section to expand.</p>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
        <strong>Important:</strong> All fiscal estimates are for informational and planning purposes only. They are not certified appraisals, official city projections, or investment advice. Figures should be verified against M&C staff reports and official Fort Worth budget documents before being used in formal analysis.
      </div>

      <div className="space-y-3">
        {sections.map(sec => {
          const c = colorMap[sec.color]
          const isOpen = open === sec.id
          return (
            <div key={sec.id} className={`border rounded-xl overflow-hidden ${c.border}`}>
              <button
                className={`w-full flex items-center justify-between px-4 py-3.5 text-left ${c.head} hover:opacity-90 transition-opacity`}
                onClick={() => setOpen(isOpen ? null : sec.id)}
              >
                <div className="flex items-center gap-3">
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${c.dot}`} />
                  <span className={`font-semibold text-sm ${c.title}`}>{sec.title}</span>
                </div>
                <span className={`text-lg leading-none ${c.title} ${isOpen ? 'rotate-180' : ''} transition-transform`}>›</span>
              </button>
              {isOpen && (
                <div className={`px-5 py-4 ${c.bg} border-t ${c.border}`}>
                  {sec.content}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
