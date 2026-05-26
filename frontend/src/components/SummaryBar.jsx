import { TrendingUp, TrendingDown, Minus, HelpCircle } from 'lucide-react'

export default function SummaryBar({ items }) {
  const counts = { POSITIVE: 0, NEUTRAL: 0, NEGATIVE: 0, UNKNOWN: 0 }
  let totalNet = 0
  let netApplicable = 0

  items.forEach(item => {
    const r = item.analysis?.fiscal_impact_rating || 'UNKNOWN'
    counts[r] = (counts[r] || 0) + 1
    if (item.analysis?.year1_net_impact != null) {
      totalNet += item.analysis.year1_net_impact
      netApplicable++
    }
  })

  function fmt(n) {
    const abs = Math.abs(n)
    const sign = n < 0 ? '-' : '+'
    if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`
    if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`
    return `${sign}$${abs.toFixed(0)}`
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-6 items-center">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-500 font-semibold uppercase tracking-wider">Agenda Summary</p>
        <p className="text-sm text-gray-700 mt-0.5">{items.length} items analyzed</p>
      </div>

      <StatChip
        count={counts.POSITIVE}
        label="Positive"
        icon={<TrendingUp className="w-4 h-4" />}
        color="text-green-700 bg-green-50 border-green-200"
      />
      <StatChip
        count={counts.NEUTRAL}
        label="Neutral"
        icon={<Minus className="w-4 h-4" />}
        color="text-yellow-700 bg-yellow-50 border-yellow-200"
      />
      <StatChip
        count={counts.NEGATIVE}
        label="Negative"
        icon={<TrendingDown className="w-4 h-4" />}
        color="text-red-700 bg-red-50 border-red-200"
      />
      <StatChip
        count={counts.UNKNOWN}
        label="N/A"
        icon={<HelpCircle className="w-4 h-4" />}
        color="text-gray-500 bg-gray-50 border-gray-200"
      />

      {netApplicable > 0 && (
        <div className="border-l border-gray-200 pl-6">
          <p className="text-xs text-gray-500">Combined Year 1 Net</p>
          <p className={`text-lg font-bold ${totalNet >= 0 ? 'text-green-700' : 'text-red-700'}`}>
            {fmt(totalNet)}
          </p>
        </div>
      )}
    </div>
  )
}

function StatChip({ count, label, icon, color }) {
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-semibold ${color}`}>
      {icon}
      <span>{count} {label}</span>
    </div>
  )
}
