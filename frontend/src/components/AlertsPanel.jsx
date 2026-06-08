import { useState, useEffect } from 'react'
import { Bell, Plus, Trash2, CheckCheck, MapPin, Building2, Tag, X } from 'lucide-react'
import {
  listAlerts, createAlert, deleteAlert,
  getAlertMatches, markAlertMatchRead, markAllAlertsRead,
} from '../services/api'

const TYPE_CONFIG = {
  district: { label: 'District', icon: Building2, color: 'bg-blue-100 text-blue-800' },
  address:  { label: 'Address',  icon: MapPin,     color: 'bg-green-100 text-green-800' },
  category: { label: 'Category', icon: Tag,        color: 'bg-purple-100 text-purple-800' },
}

export default function AlertsPanel({ onUnreadChange }) {
  const [alerts, setAlerts]   = useState([])
  const [matches, setMatches] = useState([])
  const [tab, setTab]         = useState('matches')
  const [form, setForm]       = useState({ label: '', alert_type: 'district', criteria: '' })
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState('')

  async function load() {
    const [a, m] = await Promise.all([listAlerts(), getAlertMatches()])
    setAlerts(a)
    setMatches(m)
    if (onUnreadChange) onUnreadChange(m.filter(x => !x.is_read).length)
  }

  useEffect(() => { load() }, [])

  async function handleCreate(e) {
    e.preventDefault()
    if (!form.label.trim() || !form.criteria.trim()) return
    setSaving(true)
    setError('')
    try {
      await createAlert(form.label, form.alert_type, form.criteria)
      setForm({ label: '', alert_type: 'district', criteria: '' })
      await load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create alert')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    await deleteAlert(id)
    await load()
  }

  async function handleRead(matchId) {
    await markAlertMatchRead(matchId)
    await load()
  }

  async function handleReadAll() {
    await markAllAlertsRead()
    await load()
  }

  const unread = matches.filter(m => !m.is_read).length

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-2 border-b border-gray-200">
        {['matches', 'manage'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              tab === t ? 'border-fw-blue text-fw-blue' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            {t === 'matches'
              ? <>Matches {unread > 0 && <span className="ml-1.5 bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">{unread}</span>}</>
              : 'Manage Alerts'}
          </button>
        ))}
      </div>

      {tab === 'matches' && (
        <div className="space-y-3">
          {matches.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">
              No matches yet. Create an alert to get notified when matching items appear.
            </p>
          )}
          {unread > 0 && (
            <button onClick={handleReadAll}
              className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-semibold ml-auto">
              <CheckCheck className="w-3.5 h-3.5" /> Mark all read
            </button>
          )}
          {matches.map(m => (
            <div key={m.match_id}
              className={`rounded-lg border p-3 flex items-start gap-3 transition-colors ${
                m.is_read ? 'bg-white border-gray-200' : 'bg-blue-50 border-blue-200'
              }`}>
              <Bell className={`w-4 h-4 flex-shrink-0 mt-0.5 ${m.is_read ? 'text-gray-400' : 'text-blue-500'}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-xs font-bold text-gray-700">{m.alert_label}</span>
                  <span className="text-xs text-gray-400">·</span>
                  <span className="text-xs text-gray-500">{m.meeting_date || 'Unknown date'}</span>
                </div>
                <p className="text-sm text-gray-800 leading-snug">{m.item_title}</p>
                <p className="text-xs text-gray-500 mt-1">{m.match_reason}</p>
              </div>
              {!m.is_read && (
                <button onClick={() => handleRead(m.match_id)}
                  className="text-gray-400 hover:text-gray-600 flex-shrink-0">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'manage' && (
        <div className="space-y-4">
          {/* Create form */}
          <form onSubmit={handleCreate} className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3">
            <p className="text-xs font-bold text-gray-600 uppercase tracking-wide">New Alert</p>
            <input value={form.label} onChange={e => setForm(f => ({...f, label: e.target.value}))}
              placeholder="Alert name (e.g. District 5 Zoning)"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-fw-blue" />
            <div className="flex gap-2">
              <select value={form.alert_type} onChange={e => setForm(f => ({...f, alert_type: e.target.value}))}
                className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-fw-blue">
                <option value="district">Council District</option>
                <option value="address">Address / Street</option>
                <option value="category">Category</option>
              </select>
              <input value={form.criteria} onChange={e => setForm(f => ({...f, criteria: e.target.value}))}
                placeholder={form.alert_type === 'district' ? '5' : form.alert_type === 'address' ? 'Oak Grove' : 'Zoning Change'}
                className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-fw-blue" />
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
            <button type="submit" disabled={saving}
              className="flex items-center gap-1.5 text-sm bg-fw-blue text-white px-4 py-2 rounded-lg hover:bg-blue-800 disabled:opacity-50 font-semibold">
              <Plus className="w-4 h-4" /> Add Alert
            </button>
          </form>

          {/* Existing alerts */}
          {alerts.length === 0 && <p className="text-sm text-gray-400 text-center py-4">No alerts configured.</p>}
          {alerts.map(a => {
            const cfg = TYPE_CONFIG[a.alert_type] || TYPE_CONFIG.category
            const Icon = cfg.icon
            return (
              <div key={a.id} className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 p-3">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 ${cfg.color}`}>
                  <Icon className="w-3 h-3" /> {cfg.label}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-800">{a.label}</p>
                  <p className="text-xs text-gray-500">{a.criteria}</p>
                </div>
                <button onClick={() => handleDelete(a.id)}
                  className="text-gray-400 hover:text-red-500 flex-shrink-0">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
