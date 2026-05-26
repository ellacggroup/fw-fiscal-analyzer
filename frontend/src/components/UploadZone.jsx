import { useRef, useState } from 'react'
import { Upload, FileText, Link } from 'lucide-react'

export default function UploadZone({ onUpload, onUploadUrl, loading }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [tab, setTab] = useState('file')   // 'file' | 'url'
  const [url, setUrl] = useState('')
  const [urlError, setUrlError] = useState('')

  function handleFile(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      alert('Please select a PDF file.')
      return
    }
    onUpload(file)
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    if (tab !== 'file') return
    const file = e.dataTransfer.files[0]
    handleFile(file)
  }

  function handleUrlSubmit(e) {
    e.preventDefault()
    const trimmed = url.trim()
    if (!trimmed) { setUrlError('Please enter a URL.'); return }
    if (!trimmed.startsWith('http')) { setUrlError('URL must start with http:// or https://'); return }
    setUrlError('')
    onUploadUrl(trimmed)
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      {/* Tab bar */}
      <div className="flex border-b border-gray-200">
        {[
          { id: 'file', label: 'Upload PDF', icon: Upload },
          { id: 'url',  label: 'Load from URL', icon: Link },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => !loading && setTab(id)}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-semibold transition-colors
              ${tab === id
                ? 'border-b-2 border-fw-blue text-fw-blue bg-blue-50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              } ${loading ? 'cursor-not-allowed opacity-50' : ''}`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* File drop zone */}
      {tab === 'file' && (
        <div
          onClick={() => !loading && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`p-10 text-center cursor-pointer transition-all
            ${dragging ? 'bg-blue-50' : 'hover:bg-gray-50'}
            ${loading ? 'opacity-60 cursor-not-allowed' : ''}`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => handleFile(e.target.files[0])}
          />
          <div className="flex flex-col items-center gap-3">
            {loading ? (
              <div className="w-12 h-12 border-4 border-fw-blue border-t-transparent rounded-full animate-spin" />
            ) : (
              <Upload className="w-12 h-12 text-gray-400" />
            )}
            <div>
              <p className="text-lg font-semibold text-gray-700">
                {loading ? 'Analyzing agenda…' : 'Upload City Council Agenda'}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {loading
                  ? 'Running fiscal analysis — this may take 30–60 seconds with Claude AI'
                  : 'Drag & drop a PDF here, or click to browse'}
              </p>
            </div>
            {!loading && (
              <div className="flex items-center gap-2 text-xs text-gray-400 mt-1">
                <FileText className="w-4 h-4" />
                <span>Fort Worth City Council agenda PDFs only</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* URL input */}
      {tab === 'url' && (
        <div className="p-8">
          <p className="text-sm text-gray-600 mb-4">
            Paste the direct link to a Fort Worth City Council agenda PDF.
            The city posts agendas at{' '}
            <span className="font-mono text-xs bg-gray-100 px-1 py-0.5 rounded">
              fortworthtexas.gov
            </span>{' '}
            — right-click a PDF link and copy the address.
          </p>
          <form onSubmit={handleUrlSubmit} className="flex gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setUrlError('') }}
              disabled={loading}
              placeholder="https://fortworthtexas.gov/.../agenda.pdf"
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fw-blue disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={loading || !url.trim()}
              className="bg-fw-blue text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Loading…
                </span>
              ) : 'Analyze'}
            </button>
          </form>
          {urlError && <p className="text-xs text-red-600 mt-2">{urlError}</p>}
        </div>
      )}
    </div>
  )
}
