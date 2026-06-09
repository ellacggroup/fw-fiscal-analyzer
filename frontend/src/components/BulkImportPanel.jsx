import { useState, useEffect, useRef } from 'react'
import { Download, CheckCircle, XCircle, Clock, RefreshCw, Play, FileText, RotateCcw, Youtube } from 'lucide-react'
import { startBulkImport, getBulkImportStatus, listBulkImportJobs, reprocessVotes, syncYouTubeVotes } from '../services/api'

const STATUS_ICON = {
  pending:  <Clock className="w-4 h-4 text-yellow-500" />,
  running:  <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />,
  complete: <CheckCircle className="w-4 h-4 text-green-500" />,
  error:    <XCircle className="w-4 h-4 text-red-500" />,
}

const STATUS_COLOR = {
  pending:  'bg-yellow-50 border-yellow-200',
  running:  'bg-blue-50 border-blue-200',
  complete: 'bg-green-50 border-green-200',
  error:    'bg-red-50 border-red-200',
}

export default function BulkImportPanel() {
  const [years, setYears] = useState(5)
  const [activeJob, setActiveJob] = useState(null)
  const [recentJobs, setRecentJobs] = useState([])
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => {
    listBulkImportJobs()
      .then(jobs => {
        setRecentJobs(jobs)
        // If latest job is still running, resume polling
        const latest = jobs[0]
        if (latest && (latest.status === 'running' || latest.status === 'pending')) {
          setActiveJob(latest)
          startPolling(latest.job_id)
        }
      })
      .catch(() => {})
    return () => stopPolling()
  }, [])

  function startPolling(jobId) {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const status = await getBulkImportStatus(jobId)
        setActiveJob(status)
        setRecentJobs(prev => prev.map(j => j.job_id === status.job_id ? status : j))
        if (status.status === 'complete' || status.status === 'error') {
          stopPolling()
        }
      } catch {
        stopPolling()
      }
    }, 3000)
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function handleYouTubeSync() {
    setStarting(true)
    setError(null)
    try {
      const job = await syncYouTubeVotes()
      setActiveJob(job)
      setRecentJobs(prev => [job, ...prev.slice(0, 9)])
      startPolling(job.job_id)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to start YouTube sync')
    } finally {
      setStarting(false)
    }
  }

  async function handleReprocess() {
    setStarting(true)
    setError(null)
    try {
      const job = await reprocessVotes()
      setActiveJob(job)
      setRecentJobs(prev => [job, ...prev.slice(0, 9)])
      startPolling(job.job_id)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to start reprocess')
    } finally {
      setStarting(false)
    }
  }

  async function handleStart() {
    setStarting(true)
    setError(null)
    try {
      const job = await startBulkImport(years)
      setActiveJob(job)
      setRecentJobs(prev => [job, ...prev.slice(0, 9)])
      startPolling(job.job_id)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to start import')
    } finally {
      setStarting(false)
    }
  }

  const isRunning = activeJob?.status === 'running' || activeJob?.status === 'pending'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Bulk Import from Legistar</h2>
          <p className="text-sm text-gray-500 mt-1">
            Automatically scrape all Fort Worth City Council agendas and meeting
            minutes from the past N years. Only zoning changes, economic incentives,
            land use, platting, site plans, and impact/development fees are saved.
          </p>
        </div>
        <Download className="w-8 h-8 text-fw-blue flex-shrink-0 mt-1" />
      </div>

      {/* Import config + trigger */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <h3 className="font-semibold text-gray-800">Configure Import</h3>

        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-600 whitespace-nowrap">Years back:</label>
            <select
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
              value={years}
              onChange={e => setYears(Number(e.target.value))}
              disabled={isRunning}
            >
              {[1, 2, 3, 5, 7, 10].map(y => (
                <option key={y} value={y}>{y} year{y !== 1 ? 's' : ''}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleStart}
            disabled={isRunning || starting}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
              isRunning || starting
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-fw-blue text-white hover:bg-blue-800'
            }`}
          >
            <Play className="w-4 h-4" />
            {starting ? 'Starting…' : isRunning ? 'Import Running…' : 'Start Import'}
          </button>
          <button
            onClick={handleReprocess}
            disabled={isRunning || starting}
            title="Re-run vote extraction on all imported meetings using PDF minutes"
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
              isRunning || starting
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-gray-700 text-white hover:bg-gray-900'
            }`}
          >
            <RotateCcw className="w-4 h-4" />
            Reprocess Votes
          </button>
          <button
            onClick={handleYouTubeSync}
            disabled={isRunning || starting}
            title="Pull vote pass/fail data from Fort Worth YouTube meeting transcripts (covers recent meetings)"
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
              isRunning || starting
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-red-600 text-white hover:bg-red-700'
            }`}
          >
            <Youtube className="w-4 h-4" />
            YouTube Vote Sync
          </button>
        </div>

        <div className="text-xs text-gray-400 space-y-1">
          <p>• Fetches meeting list from <strong>fortworthgov.legistar.com</strong> (public API)</p>
          <p>• Downloads agenda PDFs and meeting minutes; extracts votes + council districts</p>
          <p>• Falls back to <strong>YouTube transcripts</strong> for recent meetings without published minutes</p>
          <p>• Skips meetings already in the database</p>
          <p>• Use <strong>Reprocess Votes</strong> to re-run vote extraction on existing data after updates</p>
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}
      </div>

      {/* Active job progress */}
      {activeJob && (
        <div className={`rounded-xl border p-5 space-y-3 ${STATUS_COLOR[activeJob.status] || 'bg-gray-50 border-gray-200'}`}>
          <div className="flex items-center gap-2">
            {STATUS_ICON[activeJob.status] || <Clock className="w-4 h-4 text-gray-400" />}
            <h3 className="font-semibold text-gray-800">
              {activeJob.status === 'running' ? 'Import in Progress' :
               activeJob.status === 'complete' ? 'Import Complete' :
               activeJob.status === 'error' ? 'Import Failed' : 'Import Pending'}
            </h3>
          </div>

          {/* Progress stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Meetings Found', value: activeJob.total_meetings },
              { label: 'Agendas Processed', value: activeJob.processed_agendas },
              { label: 'Minutes Processed', value: activeJob.processed_minutes },
              { label: 'Errors', value: activeJob.errors },
            ].map(({ label, value }) => (
              <div key={label} className="bg-white/60 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-gray-900">{value ?? '—'}</p>
                <p className="text-xs text-gray-500 mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          {/* Progress bar for running jobs */}
          {activeJob.status === 'running' && activeJob.total_meetings > 0 && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-gray-500">
                <span>Progress</span>
                <span>
                  {Math.round(
                    ((activeJob.processed_agendas + activeJob.processed_minutes + activeJob.skipped) /
                      activeJob.total_meetings) * 100
                  )}%
                </span>
              </div>
              <div className="w-full bg-white/50 rounded-full h-2">
                <div
                  className="bg-fw-blue rounded-full h-2 transition-all duration-500"
                  style={{
                    width: `${Math.min(100, Math.round(
                      ((activeJob.processed_agendas + activeJob.processed_minutes + activeJob.skipped) /
                        activeJob.total_meetings) * 100
                    ))}%`
                  }}
                />
              </div>
            </div>
          )}

          {/* Log output */}
          {activeJob.log && activeJob.log.length > 0 && (
            <div className="bg-white/70 rounded-lg p-3 max-h-48 overflow-y-auto font-mono text-xs text-gray-700 space-y-0.5">
              {activeJob.log.slice(-30).map((line, i) => (
                <div key={i} className={line.includes('ERROR') ? 'text-red-600' : line.includes('complete') ? 'text-green-700 font-semibold' : ''}>
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Recent jobs table */}
      {recentJobs.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <h3 className="font-semibold text-gray-800 text-sm">Recent Import Jobs</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2 text-left">Started</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-right">Agendas</th>
                <th className="px-4 py-2 text-right">Minutes</th>
                <th className="px-4 py-2 text-right">Errors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {recentJobs.map(job => (
                <tr key={job.job_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-600">
                    {job.started_at ? new Date(job.started_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <span className="flex items-center gap-1.5">
                      {STATUS_ICON[job.status]}
                      <span className="capitalize text-gray-700">{job.status}</span>
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-700">{job.processed_agendas ?? '—'}</td>
                  <td className="px-4 py-2 text-right text-gray-700">{job.processed_minutes ?? '—'}</td>
                  <td className="px-4 py-2 text-right text-red-600">{job.errors ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Info box */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800 space-y-1">
        <p className="font-semibold">What gets imported</p>
        <p>Only items in these categories are saved to the database:</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 mt-1">
          <ul className="list-disc list-inside ml-2 space-y-0.5 text-blue-700">
            <li>Zoning Changes (ZC cases)</li>
            <li>Site Plans (SP cases)</li>
            <li>Platting (final/preliminary plats)</li>
            <li>Land Use / Comp Plan amendments</li>
            <li>Economic Incentives (Ch. 380, abatements)</li>
            <li>Development Agreements</li>
            <li>TIRZ / Tax Increment Financing</li>
          </ul>
          <ul className="list-disc list-inside ml-2 space-y-0.5 text-blue-700">
            <li>Public Improvement Districts (PIDs)</li>
            <li>Impact & Development Fees</li>
            <li>Annexation</li>
            <li>Right-of-Way & Easement actions</li>
            <li>City Land Acquisition / Disposition</li>
            <li>Utility Extensions (water/sewer)</li>
            <li>Development Code / Standards changes</li>
          </ul>
        </div>
        <p className="mt-2 text-blue-600 text-xs">
          Votes are extracted from meeting minutes and linked to each case.
          After import, visit the <strong>Trends</strong> tab to analyze 5-year patterns.
        </p>
      </div>
    </div>
  )
}
