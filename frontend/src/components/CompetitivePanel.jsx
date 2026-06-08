import { useState, useEffect } from 'react'
import { MapPin, Plus, Trash2, AlertTriangle, CheckCircle } from 'lucide-react'
import {
  listWatchedProperties, addWatchedProperty, deleteWatchedProperty,
  getProximityAlerts, markProximityAlertRead,
} from '../services/api'

export default function CompetitivePanel({ onUnreadChange }) {
  const [properties, setProperties] = useState([])
  const [alerts, setAlerts]         = useState([])
  const [tab, setTab]               = useState('alerts')
  const [form, setForm]             = useState({ label: '', address: '', radius_miles: '1.0' })
  const [saving, setSaving]         = useState(false)
  const [error, setError]           = useState('')

  async function load() {
    const [props, alts] = await Promise.all([listWatchedProperties(), getProximityAlerts()])
    setProperties(props)
    setAlerts(alts)
    if (onUnreadChange) onUnreadChange(alts.filter(a => !a.is_read).length)
  }

  useEffect(() => { load() }, [])

  async function handleAdd(e) {
    e.preventDefault()
    if (!form.label.trim() || !form.address.trim()) return
    setSaving(true)
    setError('')
    try {
      await addWatchedProperty(form.label, form.address, parseFloat(form.radius_miles) || 1.0)
      setForm({ label: '', address: '', radius_miles: '1.0' })
      await load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add property')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    await deleteWatchedProperty(id)
    await load()
  }

  async function handleRead(alertId) {
    await markProximityAlertRead(alertId)
    await load()
  }

  const unread = alerts.filter(a => !a.is_read).length

  return (
    <div className="space-y-4">
      <div className="flex gap-2 border-b border-gray-200">
        {['alerts', 'properties'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              tab === t ? 'border-fw-blue text-fw-blue' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            {t === 'alerts'
              ? <>Proximity Alerts {unread > 0 && <span className="ml-1.5 bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">{unread}</span>}</>
              : 'Watched Properties'}
          </button>
        ))}
      </div>

      {tab === 'alerts' && (
        <div className="space-y-3">
          {alerts.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">
              No proximity alerts. Add watched properties and upload agendas to detect nearby deals.
            </p>
          )}
          {alerts.map(a => (
            <div key={a.alert_id}
              className={`rounded-xl border p-4 space-y-2 transition-colors ${
                a.is_read ? 'bg-white border-gray-200' : 'bg-amber-50 border-amber-300'
              }`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <AlertTriangle className={`w-4 h-4 flex-shrink-0 ${a.is_read ? 'text-gray-400' : 'text-amber-600'}`} />
                  <div>
                    <p className="text-xs font-bold text-gray-700">{a.property_label}</p>
                    <p className="text-xs text-gray-500">{a.property_address} · {a.radius_miles} mi radius</p>
                  </div>
                </div>
                {!a.is_read && (
                  <button onClick={() => handleRead(a.alert_id)}
                    className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1 flex-shrink-0">
                    <CheckCircle className="w-3.5 h-3.5" /> Dismiss
                  </button>
                )}
              </div>
              <p className="text-sm text-gray-900 font-semibold">{a.item_title}</p>
              <div className="flex flex-wrap gap-3 text-xs">
                <span className="text-gray-500">{a.meeting_date}</span>
                {a.deal_type && (
                  <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full font-semibold">{a.deal_type}</span>
                )}
                {a.distance_miles != null && (
                  <span className="flex items-center gap-1 text-gray-600">
                    <MapPin className="w-3 h-3" /> {a.distance_miles.toFixed(2)} miles away
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'properties' && (
        <div className="space-y-4">
          <form onSubmit={handleAdd} className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3">
            <p className="text-xs font-bold text-gray-600 uppercase tracking-wide">Add Watched Property</p>
            <input value={form.label} onChange={e => setForm(f => ({...f, label: e.target.value}))}
              placeholder="Property name / label"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-fw-blue" />
            <input value={form.address} onChange={e => setForm(f => ({...f, address: e.target.value}))}
              placeholder="Full address (e.g. 2929 W Berry St, Fort Worth, TX)"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-fw-blue" />
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-600 flex-shrink-0">Alert radius (miles):</label>
              <input type="number" step="0.25" min="0.25" max="10"
                value={form.radius_miles}
                onChange={e => setForm(f => ({...f, radius_miles: e.target.value}))}
                className="w-20 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-fw-blue" />
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
            <button type="submit" disabled={saving}
              className="flex items-center gap-1.5 text-sm bg-fw-blue text-white px-4 py-2 rounded-lg hover:bg-blue-800 disabled:opacity-50 font-semibold">
              <Plus className="w-4 h-4" /> Add Property
            </button>
          </form>

          {properties.length === 0 && <p className="text-sm text-gray-400 text-center py-4">No properties being watched.</p>}
          {properties.map(p => (
            <div key={p.id} className="flex items-start gap-3 bg-white rounded-lg border border-gray-200 p-3">
              <MapPin className={`w-4 h-4 flex-shrink-0 mt-0.5 ${p.geocoded ? 'text-green-500' : 'text-gray-400'}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800">{p.label}</p>
                <p className="text-xs text-gray-500">{p.address}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {p.radius_miles} mile radius ·{' '}
                  {p.geocoded
                    ? <span className="text-green-600">Geocoded ✓</span>
                    : <span className="text-amber-600">Not geocoded — alerts may not work</span>}
                </p>
              </div>
              <button onClick={() => handleDelete(p.id)} className="text-gray-400 hover:text-red-500 flex-shrink-0">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
