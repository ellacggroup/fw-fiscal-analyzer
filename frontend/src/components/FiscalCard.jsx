import { useState } from 'react'
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus, HelpCircle, AlertCircle, RefreshCw, Calendar, ArrowRight, MapPin, DollarSign, Briefcase, Map, ExternalLink } from 'lucide-react'

const RATING_CONFIG = {
  POSITIVE: {
    label: 'Fiscally Positive',
    bg: 'bg-green-50',
    border: 'border-green-300',
    badge: 'bg-green-100 text-green-800',
    icon: TrendingUp,
    iconColor: 'text-green-600',
    dot: 'bg-green-500',
  },
  NEUTRAL: {
    label: 'Fiscally Neutral',
    bg: 'bg-yellow-50',
    border: 'border-yellow-300',
    badge: 'bg-yellow-100 text-yellow-800',
    icon: Minus,
    iconColor: 'text-yellow-600',
    dot: 'bg-yellow-500',
  },
  NEGATIVE: {
    label: 'Fiscally Negative',
    bg: 'bg-red-50',
    border: 'border-red-300',
    badge: 'bg-red-100 text-red-800',
    icon: TrendingDown,
    iconColor: 'text-red-600',
    dot: 'bg-red-500',
  },
  UNKNOWN: {
    label: 'No Direct Fiscal Impact',
    bg: 'bg-gray-50',
    border: 'border-gray-200',
    badge: 'bg-gray-100 text-gray-600',
    icon: HelpCircle,
    iconColor: 'text-gray-400',
    dot: 'bg-gray-400',
  },
}

function fmt(n) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : '+'
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`
  return `${sign}$${abs.toFixed(0)}`
}

function fmtRatio(r) {
  if (r == null) return '—'
  return r.toFixed(2)
}

export default function FiscalCard({ item }) {
  const [expanded, setExpanded] = useState(false)
  const analysis = item.analysis || {}
  const rating = analysis.fiscal_impact_rating || 'UNKNOWN'
  const cfg = RATING_CONFIG[rating] || RATING_CONFIG.UNKNOWN
  const Icon = cfg.icon

  const confidence = analysis.confidence
  const confidenceBadge = {
    HIGH: 'bg-blue-100 text-blue-700',
    MEDIUM: 'bg-orange-100 text-orange-700',
    LOW: 'bg-red-100 text-red-700',
  }[confidence] || 'bg-gray-100 text-gray-600'

  const risk = analysis.risk_level
  const riskBadge = {
    LOW:    'bg-green-100 text-green-700',
    MEDIUM: 'bg-yellow-100 text-yellow-800',
    HIGH:   'bg-red-100 text-red-700',
  }[risk] || ''

  const isRecurring = analysis.is_recurring
  const primaryNarrative = analysis.claude_summary || analysis.analysis_narrative || ''

  return (
    <div className={`rounded-xl border-2 ${cfg.border} ${cfg.bg} overflow-hidden transition-all`}>
      {/* Header row */}
      <div
        className="p-4 cursor-pointer select-none"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-start gap-3">
          <div className={`mt-1 w-3 h-3 rounded-full flex-shrink-0 ${cfg.dot}`} />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              {item.item_number && (
                <span className="text-xs font-mono font-bold text-gray-500 bg-white border border-gray-200 rounded px-1.5 py-0.5">
                  #{item.item_number}
                </span>
              )}
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.badge}`}>
                {cfg.label}
              </span>
              {confidence && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${confidenceBadge}`}>
                  {confidence} confidence
                </span>
              )}
              {risk && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${riskBadge}`}>
                  {risk} risk
                </span>
              )}
              {isRecurring === true && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 flex items-center gap-1">
                  <RefreshCw className="w-3 h-3" /> Recurring
                </span>
              )}
              {isRecurring === false && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 flex items-center gap-1">
                  <Calendar className="w-3 h-3" /> One-time
                </span>
              )}
              <span className="text-xs text-gray-500 bg-white border border-gray-200 rounded px-1.5 py-0.5">
                {item.category}
              </span>
            </div>
            <h3 className="font-semibold text-gray-900 leading-snug">{item.title}</h3>
          </div>
          <div className="flex-shrink-0 flex items-center gap-3 ml-2">
            <Icon className={`w-5 h-5 ${cfg.iconColor}`} />
            {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </div>
        </div>

        {/* Quick metrics row */}
        {rating !== 'UNKNOWN' && (
          <div className="mt-3 ml-5 flex flex-wrap gap-4">
            <Metric label="Year 1 Net" value={fmt(analysis.year1_net_impact)} highlight />
            <Metric label="R/C Ratio" value={fmtRatio(analysis.revenue_to_cost_ratio)} />
            <Metric label="40-yr Net" value={fmt(analysis.projection_40yr_net)} />
            {analysis.break_even_year != null && (
              <Metric label="Break-even" value={`Yr ${analysis.break_even_year}`} />
            )}
          </div>
        )}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t-2 border-white bg-white/60 px-5 py-4 space-y-4">
          {primaryNarrative && (
            <p className="text-sm text-gray-700 leading-relaxed">{primaryNarrative}</p>
          )}

          {/* If Claude summary and rule-based narrative are both present, show rule-based as secondary */}
          {analysis.claude_summary && analysis.analysis_narrative && (
            <details className="group">
              <summary className="text-xs font-semibold text-gray-400 cursor-pointer hover:text-gray-600 list-none flex items-center gap-1 mt-1">
                <ChevronDown className="w-3 h-3 group-open:rotate-180 transition-transform" />
                Rule-based analysis detail
              </summary>
              <p className="mt-2 text-xs text-gray-500 leading-relaxed">{analysis.analysis_narrative}</p>
            </details>
          )}

          {/* Key concerns from Claude */}
          {analysis.key_concerns?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-1">
              {analysis.key_concerns.map((c, i) => (
                <span key={i} className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded px-2 py-0.5">
                  ⚑ {c}
                </span>
              ))}
            </div>
          )}

          {/* One-time vs recurring note */}
          {analysis.one_time_vs_recurring_note && (
            <p className="text-xs text-gray-500 italic">{analysis.one_time_vs_recurring_note}</p>
          )}

          {/* ── Annexation hearing notice ── */}
          {analysis.annexation_hearing && (
            <div className="rounded-xl border-2 border-amber-200 bg-amber-50 p-4">
              <p className="text-xs font-bold text-amber-800 uppercase tracking-wide mb-1">
                Procedural Step — No Direct Fiscal Impact
              </p>
              <p className="text-sm text-amber-900 leading-relaxed">
                This item conducts the public hearing required by Texas law before an
                annexation can be approved. The hearing itself does not change the city's
                finances. Look for the <strong>annexation ordinance or resolution</strong> item
                (usually a separate agenda item) for the actual fiscal impact analysis.
              </p>
            </div>
          )}

          {/* ── Comprehensive Plan Land Use ── */}
          {(analysis.comp_plan_relevant || analysis.comp_plan_lu_code || analysis.comp_plan_lookup_status) && (
            <CompPlanSection analysis={analysis} />
          )}

          {/* ── Site plan / plat two-tier analysis ── */}
          {analysis.site_plan_type && (
            <SitePlanDetail analysis={analysis} />
          )}

          {/* ── Zoning Request Detail ── */}
          {analysis.zoning_request_parsed && (
            <ZoningDetail analysis={analysis} />
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Revenue & Costs */}
            {rating !== 'UNKNOWN' && (
              <DetailSection title="Financial Estimates (Year 1)">
                <DetailRow label="Revenue" value={analysis.year1_revenue_estimate != null ? `$${analysis.year1_revenue_estimate.toLocaleString()}` : '—'} />
                <DetailRow label="Costs" value={analysis.year1_cost_estimate != null ? `$${analysis.year1_cost_estimate.toLocaleString()}` : '—'} />
                <DetailRow label="Net Impact" value={fmt(analysis.year1_net_impact)} bold />
              </DetailSection>
            )}

            {/* Land use */}
            {analysis.land_use_type && analysis.land_use_type !== 'N/A' && (
              <DetailSection title="Land Use Details">
                <DetailRow label="Type" value={analysis.land_use_type} />
                {analysis.acreage_estimate != null && (
                  <DetailRow label="Estimated Acres" value={`${analysis.acreage_estimate.toLocaleString()} ac`} />
                )}
                {analysis.units_or_sqft_estimate != null && (
                  <DetailRow label="Units / Sq Ft" value={analysis.units_or_sqft_estimate.toLocaleString()} />
                )}
              </DetailSection>
            )}

            {/* Revenue sources */}
            {analysis.key_revenue_sources?.length > 0 && (
              <DetailSection title="Key Revenue Sources">
                <TagList items={analysis.key_revenue_sources} color="green" />
              </DetailSection>
            )}

            {/* Cost drivers */}
            {analysis.key_cost_drivers?.length > 0 && (
              <DetailSection title="Key Cost Drivers">
                <TagList items={analysis.key_cost_drivers} color="red" />
              </DetailSection>
            )}

            {/* Departments */}
            {analysis.departments_impacted?.length > 0 && (
              <DetailSection title="Departments Impacted">
                <TagList items={analysis.departments_impacted} color="blue" />
              </DetailSection>
            )}

            {/* Infrastructure */}
            {analysis.infrastructure_requirements && (
              <DetailSection title="Infrastructure Requirements">
                <p className="text-sm text-gray-600">{analysis.infrastructure_requirements}</p>
              </DetailSection>
            )}
          </div>

          {/* Description */}
          {item.description && (
            <details className="group">
              <summary className="text-xs font-semibold text-gray-500 cursor-pointer hover:text-gray-700 list-none flex items-center gap-1">
                <ChevronDown className="w-3 h-3 group-open:rotate-180 transition-transform" />
                Agenda item description
              </summary>
              <p className="mt-2 text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">{item.description}</p>
            </details>
          )}

          {/* Caveats */}
          {analysis.caveats && (
            <div className="flex gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{analysis.caveats}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value, highlight }) {
  return (
    <div className="text-center">
      <div className={`text-sm font-bold ${highlight ? 'text-gray-900' : 'text-gray-700'}`}>{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  )
}

function DetailSection({ title, children }) {
  return (
    <div>
      <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-2">{title}</h4>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function DetailRow({ label, value, bold }) {
  return (
    <div className="flex justify-between text-sm gap-2">
      <span className="text-gray-500">{label}</span>
      <span className={`${bold ? 'font-semibold' : ''} text-gray-800 text-right`}>{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Comprehensive Plan Land Use component
// ---------------------------------------------------------------------------

const LU_COLORS = {
  // Residential
  SF: 'bg-amber-50 border-amber-300 text-amber-900',
  SUB: 'bg-amber-50 border-amber-300 text-amber-900',
  RURAL: 'bg-amber-50 border-amber-300 text-amber-900',
  LDR: 'bg-yellow-50 border-yellow-300 text-yellow-900',
  MDR: 'bg-orange-50 border-orange-300 text-orange-900',
  HDR: 'bg-orange-100 border-orange-400 text-orange-900',
  UR: 'bg-orange-50 border-orange-300 text-orange-900',
  MH: 'bg-amber-50 border-amber-300 text-amber-900',
  // Commercial / Mixed
  NC: 'bg-red-50 border-red-300 text-red-900',
  GC: 'bg-red-100 border-red-400 text-red-900',
  MU: 'bg-purple-50 border-purple-300 text-purple-900',
  MUGC: 'bg-purple-100 border-purple-400 text-purple-900',
  // Industrial
  LI: 'bg-slate-50 border-slate-300 text-slate-900',
  HI: 'bg-slate-100 border-slate-400 text-slate-900',
  IGC: 'bg-slate-100 border-slate-400 text-slate-900',
  // Civic / Open
  INST: 'bg-blue-50 border-blue-300 text-blue-900',
  INFRA: 'bg-gray-50 border-gray-300 text-gray-700',
  PUBPK: 'bg-green-50 border-green-300 text-green-900',
  PRIPK: 'bg-green-50 border-green-300 text-green-900',
  AG: 'bg-lime-50 border-lime-300 text-lime-900',
  WATER: 'bg-sky-50 border-sky-300 text-sky-900',
}

function CompPlanSection({ analysis: a }) {
  const status = a.comp_plan_lookup_status
  const found = status === 'found'
  const colorClass = found
    ? (LU_COLORS[a.comp_plan_lu_code] || 'bg-gray-50 border-gray-300 text-gray-800')
    : 'bg-slate-50 border-slate-200 text-slate-700'

  return (
    <div className={`rounded-xl border-2 p-4 space-y-3 ${colorClass}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Map className="w-4 h-4 flex-shrink-0 opacity-70" />
          <h4 className="text-sm font-bold uppercase tracking-wide opacity-80">
            Comprehensive Plan — Future Land Use
          </h4>
        </div>
        <a
          href={a.comp_plan_map_url || 'https://cfw.maps.arcgis.com/apps/webappviewer/index.html?id=653d3a58efc848a1ad1e7516ee56c509'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs font-semibold underline underline-offset-2 hover:opacity-80 transition-opacity flex-shrink-0"
        >
          View CFW comp plan map <ExternalLink className="w-3 h-3" />
        </a>
      </div>

      {/* Designation — shown when lookup succeeded */}
      {found && (
        <div className="flex flex-wrap gap-3 items-start">
          <div className="bg-white/70 rounded-lg border border-current/20 px-4 py-3 flex-shrink-0">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-0.5">Designated Use</p>
            <p className="text-xl font-black">{a.comp_plan_lu_label}</p>
            <p className="text-xs font-mono opacity-60 mt-0.5">{a.comp_plan_lu_code}</p>
          </div>
          <div className="flex-1 min-w-[180px]">
            {a.comp_plan_lu_description && (
              <p className="text-sm leading-relaxed opacity-90">{a.comp_plan_lu_description}</p>
            )}
            {a.comp_plan_mu_category && (
              <p className="text-xs mt-1 opacity-70">
                Mixed-use sub-category: <strong>{a.comp_plan_mu_category}</strong>
              </p>
            )}
            {a.comp_plan_address && (
              <p className="text-xs mt-2 flex items-start gap-1 opacity-60">
                <MapPin className="w-3 h-3 flex-shrink-0 mt-0.5" />
                {a.comp_plan_address}
              </p>
            )}
          </div>
        </div>
      )}

      {/* No address extracted */}
      {status === 'no_address' && (
        <p className="text-sm text-slate-500 leading-relaxed">
          No specific street address could be extracted from this item.
          Use the map link above to look up the parcel manually.
        </p>
      )}

      {/* Address found but geocode/layer returned no result */}
      {status === 'no_match' && (
        <div className="space-y-1">
          <p className="text-sm text-slate-500 leading-relaxed">
            Could not retrieve a comp plan designation for this address
            {a.comp_plan_address ? ` (${a.comp_plan_address})` : ''}.
            The parcel may be outside Fort Worth city limits, or the address
            format wasn't recognized by the geocoder.
          </p>
          {a.comp_plan_address && (
            <p className="text-xs flex items-start gap-1 text-slate-400">
              <MapPin className="w-3 h-3 flex-shrink-0 mt-0.5" />
              Attempted: {a.comp_plan_address}
            </p>
          )}
        </div>
      )}

      <p className="text-[10px] opacity-50 leading-snug">
        Source: City of Fort Worth 2023 Adopted Comprehensive Plan — Future Land Use layer.
        Designation reflects the long-range vision for this parcel, not current zoning.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Site Plan / Plat two-tier component
// ---------------------------------------------------------------------------

function SitePlanDetail({ analysis: a }) {
  const [showBroader, setShowBroader] = useState(false)
  const bd = a.broader_development

  return (
    <div className="rounded-xl border-2 border-teal-200 bg-teal-50 p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h4 className="text-sm font-bold text-teal-900 uppercase tracking-wide">
          {a.site_plan_type} Analysis
        </h4>
        {a.site_plan_is_reorganization && (
          <span className="text-xs bg-gray-100 text-gray-600 border border-gray-200 px-2 py-0.5 rounded-full font-semibold">
            Reorganisation — no new development
          </span>
        )}
      </div>

      {/* Tier 1: Direct parcel impact */}
      <div className="bg-white rounded-lg border border-teal-200 p-3">
        <p className="text-xs font-bold text-teal-700 uppercase mb-2">
          Tier 1 — This property only
        </p>
        <p className="text-xs text-gray-600 leading-relaxed">{a.analysis_narrative}</p>
        {!a.site_plan_is_reorganization && a.year1_net_impact != null && (
          <div className="flex flex-wrap gap-4 mt-3">
            <div>
              <p className="text-[10px] text-gray-400 uppercase">Annual net (once built)</p>
              <p className={`text-sm font-bold ${a.year1_net_impact >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                {fmtNet(a.year1_net_impact)}
              </p>
            </div>
            {a.projection_40yr_net != null && (
              <div>
                <p className="text-[10px] text-gray-400 uppercase">40-yr NPV</p>
                <p className={`text-sm font-bold ${a.projection_40yr_net >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                  {fmtNet(a.projection_40yr_net)}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tier 2: Broader development (only if applicable) */}
      {bd && !a.site_plan_is_reorganization && (
        <div>
          <button
            onClick={() => setShowBroader(s => !s)}
            className="w-full flex items-center justify-between bg-white border border-teal-200 rounded-lg px-4 py-2.5 text-sm font-semibold text-teal-800 hover:bg-teal-50 transition-colors"
          >
            <span>Tier 2 — Broader development potential (speculative)</span>
            {showBroader
              ? <ChevronUp className="w-4 h-4 flex-shrink-0" />
              : <ChevronDown className="w-4 h-4 flex-shrink-0" />}
          </button>

          {showBroader && (
            <div className="bg-white border border-teal-200 rounded-lg p-4 mt-1 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-teal-700">{bd.scenario_label}</span>
                <span className="text-[10px] bg-amber-100 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded-full font-bold">
                  LOW confidence · speculative
                </span>
              </div>

              <p className="text-xs text-gray-600 leading-relaxed">{bd.scenario_description}</p>

              <div className="flex flex-wrap gap-4">
                {bd.estimated_annual_net != null && (
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Potential annual net</p>
                    <p className={`text-sm font-bold ${bd.estimated_annual_net >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                      {fmtNet(bd.estimated_annual_net)}
                    </p>
                  </div>
                )}
                {bd.estimated_40yr_npv != null && (
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">40-yr potential NPV</p>
                    <p className={`text-sm font-bold ${bd.estimated_40yr_npv >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                      {fmtNet(bd.estimated_40yr_npv)}
                    </p>
                  </div>
                )}
                {bd.estimated_jobs > 0 && (
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Potential jobs</p>
                    <p className="text-sm font-bold text-gray-700">~{bd.estimated_jobs}</p>
                  </div>
                )}
                {bd.timeline && (
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Timeline</p>
                    <p className="text-sm font-semibold text-gray-600">{bd.timeline}</p>
                  </div>
                )}
              </div>

              <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{bd.caveat}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Zoning Detail component
// ---------------------------------------------------------------------------

function fmtNet(n) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n >= 0 ? '+' : '-'
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(0)}K`
  return `${sign}$${abs}`
}

const APPROVAL_COLORS = {
  green:  'bg-green-100 text-green-800 border-green-300',
  yellow: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  blue:   'bg-blue-100 text-blue-800 border-blue-300',
}

function ZoningDetail({ analysis: a }) {
  const [showScenarios, setShowScenarios] = useState(false)
  const scenarios = a.by_right_scenarios || []
  const statedFiscal = a.stated_use_fiscal
  const isPdAmend = a.zoning_from_code === a.zoning_to_code && a.zoning_from_code?.startsWith('PD')

  return (
    <div className="rounded-xl border-2 border-indigo-200 bg-indigo-50 p-4 space-y-5">
      <h4 className="text-sm font-bold text-indigo-900 uppercase tracking-wide">
        {isPdAmend ? 'PD Amendment Detail' : 'Zoning Request Detail'}
      </h4>

      {/* From → To */}
      <div className="flex items-stretch gap-3 flex-wrap">
        <div className="flex-1 min-w-[140px] bg-white rounded-lg border border-indigo-200 p-3">
          <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">
            {isPdAmend ? 'Existing PD' : 'Current Zoning'}
          </p>
          <p className="text-sm font-bold text-gray-800 font-mono">{a.zoning_from_code}</p>
          <p className="text-sm text-gray-600 mt-0.5">{a.zoning_from_label}</p>
          {a.zoning_from_desc && a.zoning_from_desc !== a.zoning_from_label && (
            <p className="text-xs text-gray-400 mt-1 leading-snug">{a.zoning_from_desc}</p>
          )}
        </div>
        <div className="flex items-center flex-shrink-0">
          <ArrowRight className="w-5 h-5 text-indigo-400" />
        </div>
        <div className="flex-1 min-w-[140px] bg-indigo-100 rounded-lg border-2 border-indigo-300 p-3">
          <p className="text-[10px] font-bold text-indigo-500 uppercase mb-1">
            {isPdAmend ? 'Proposed Amendments' : 'Proposed Zoning'}
          </p>
          <p className="text-sm font-bold text-indigo-900 font-mono">{a.zoning_to_code}</p>
          <p className="text-sm text-indigo-700 mt-0.5">{a.zoning_to_label}</p>
          {a.zoning_to_desc && a.zoning_to_desc !== a.zoning_to_label && (
            <p className="text-xs text-indigo-500 mt-1 leading-snug">{a.zoning_to_desc}</p>
          )}
        </div>
      </div>

      {/* Approval type + vacancy row */}
      <div className="flex flex-wrap gap-3">
        {a.approval_label && (
          <div>
            <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Approval Type</p>
            <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${APPROVAL_COLORS[a.approval_color] || APPROVAL_COLORS.blue}`}>
              {a.approval_short}
            </span>
          </div>
        )}
        {a.vacancy_status && (
          <div>
            <p className="text-[10px] font-bold text-gray-400 uppercase mb-1">Property Status</p>
            <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
              a.vacancy_status === 'Likely Vacant'   ? 'bg-emerald-100 text-emerald-800 border-emerald-300' :
              a.vacancy_status === 'Likely Occupied' ? 'bg-amber-100 text-amber-800 border-amber-300' :
                                                       'bg-gray-100 text-gray-600 border-gray-200'
            }`}>
              {a.vacancy_status}
            </span>
          </div>
        )}
      </div>

      {/* Approval / vacancy explanation */}
      {a.approval_explanation && (
        <p className="text-xs text-gray-600 leading-relaxed bg-white rounded-lg p-3 border border-indigo-100">
          {a.approval_explanation}
        </p>
      )}
      {a.vacancy_rationale && a.vacancy_status === 'Unknown' && (
        <p className="text-xs text-gray-500 italic">{a.vacancy_rationale}</p>
      )}

      {/* Revenue explanation */}
      {a.revenue_explanation && (
        <div className="flex items-start gap-2">
          <DollarSign className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-gray-700 leading-relaxed">{a.revenue_explanation}</p>
        </div>
      )}

      {/* ── Stated use fiscal impact ── */}
      {a.stated_use && statedFiscal && (
        <div className="bg-white rounded-xl border-2 border-indigo-300 p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <p className="text-[10px] font-bold text-indigo-500 uppercase">Detected Use</p>
              <p className="text-base font-bold text-indigo-900">{a.stated_use}</p>
            </div>
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
              a.stated_use_confidence === 'HIGH' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
            }`}>
              {a.stated_use_confidence} confidence match
            </span>
          </div>

          <p className="text-xs text-indigo-600 leading-relaxed">{statedFiscal.texas_tax_note}</p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <FiscalStat label="Annual property tax" value={`$${statedFiscal.annual_property_tax?.toLocaleString()}`} />
            <FiscalStat
              label="Annual sales tax"
              value={statedFiscal.sales_tax_generating ? `$${statedFiscal.annual_sales_tax?.toLocaleString()}` : 'None — service use'}
              dimmed={!statedFiscal.sales_tax_generating}
            />
            <FiscalStat
              label="Annual net to city"
              value={fmtNet(statedFiscal.annual_net)}
              color={statedFiscal.annual_net >= 0 ? 'text-green-700' : 'text-red-700'}
              bold
            />
            <FiscalStat
              label="40-yr NPV"
              value={fmtNet(statedFiscal.npv_40yr)}
              color={statedFiscal.npv_40yr >= 0 ? 'text-green-700' : 'text-red-700'}
            />
          </div>

          {statedFiscal.jobs_estimate > 0 && (
            <p className="text-xs text-gray-500">
              <Briefcase className="w-3 h-3 inline mr-1" />
              Estimated <strong>{statedFiscal.jobs_estimate} direct jobs</strong> for this use type on {statedFiscal.acreage?.toFixed(2)} acres.
            </p>
          )}
        </div>
      )}

      {/* ── By-right scenarios ── */}
      {scenarios.length > 0 && (
        <div className="space-y-2">
          <button
            onClick={() => setShowScenarios(s => !s)}
            className="w-full flex items-center justify-between bg-white border border-indigo-200 rounded-lg px-4 py-2.5 text-sm font-semibold text-indigo-800 hover:bg-indigo-50 transition-colors"
          >
            <span>
              {a.stated_use
                ? `Compare: all ${scenarios.length} by-right uses under ${a.zoning_to_code}`
                : `No specific use detected — fiscal range for all ${scenarios.length} by-right uses under ${a.zoning_to_code}`}
            </span>
            {showScenarios
              ? <ChevronUp className="w-4 h-4 flex-shrink-0" />
              : <ChevronDown className="w-4 h-4 flex-shrink-0" />}
          </button>

          {showScenarios && (
            <div className="overflow-x-auto rounded-lg border border-indigo-200 bg-white">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-indigo-800 text-white text-left">
                    <th className="px-3 py-2 font-semibold">Use</th>
                    <th className="px-3 py-2 font-semibold text-center">Sales Tax?</th>
                    <th className="px-3 py-2 font-semibold text-right">Annual Revenue</th>
                    <th className="px-3 py-2 font-semibold text-right">Annual Net</th>
                    <th className="px-3 py-2 font-semibold text-right">40-yr NPV</th>
                    <th className="px-3 py-2 font-semibold text-right">Est. Jobs</th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.map((s, i) => {
                    const isStated = s.use_name === a.stated_use
                    return (
                      <tr
                        key={i}
                        className={`border-t border-indigo-100 ${
                          isStated ? 'bg-indigo-50 font-semibold' :
                          i % 2 === 0 ? 'bg-white' : 'bg-gray-50'
                        }`}
                      >
                        <td className="px-3 py-2">
                          {s.use_name}
                          {isStated && (
                            <span className="ml-2 text-[10px] bg-indigo-200 text-indigo-800 px-1.5 py-0.5 rounded-full">detected</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {s.sales_tax_generating
                            ? <span className="text-green-700 font-bold">Yes</span>
                            : <span className="text-gray-400">No</span>}
                        </td>
                        <td className="px-3 py-2 text-right">${s.annual_gross_revenue?.toLocaleString()}</td>
                        <td className={`px-3 py-2 text-right font-bold ${s.annual_net >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                          {fmtNet(s.annual_net)}
                        </td>
                        <td className={`px-3 py-2 text-right ${s.npv_40yr >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                          {fmtNet(s.npv_40yr)}
                        </td>
                        <td className="px-3 py-2 text-right">{s.jobs_estimate > 0 ? `~${s.jobs_estimate}` : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="text-[10px] text-gray-400 p-3 border-t border-gray-100">
                Sorted best-to-worst annual net fiscal impact. Estimates assume full build-out on {scenarios[0]?.acreage?.toFixed(2)} acres.
                Property tax uses Tarrant CAD benchmark values. Sales tax uses Texas Comptroller taxable-sales benchmarks.
                Actual impact depends on the specific tenant, market rents, and build-out timeline.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function FiscalStat({ label, value, color, bold, dimmed }) {
  return (
    <div className="bg-indigo-50 rounded-lg p-2.5">
      <p className="text-[10px] text-gray-400 font-semibold uppercase leading-tight">{label}</p>
      <p className={`text-sm mt-0.5 ${bold ? 'font-bold' : 'font-semibold'} ${color || ''} ${dimmed ? 'text-gray-400' : 'text-gray-800'}`}>
        {value}
      </p>
    </div>
  )
}

function TagList({ items, color }) {
  const colors = {
    green: 'bg-green-100 text-green-800',
    red: 'bg-red-100 text-red-800',
    blue: 'bg-blue-100 text-blue-800',
  }
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item, i) => (
        <span key={i} className={`text-xs px-2 py-0.5 rounded-full ${colors[color]}`}>{item}</span>
      ))}
    </div>
  )
}
