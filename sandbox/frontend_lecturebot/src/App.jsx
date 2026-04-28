import { useState, useEffect, useCallback } from 'react'
import './index.css'
import { api } from './api'
import { UploadPanel } from './components/UploadPanel'
import { ChatWindow } from './components/ChatWindow'
import { InputBar } from './components/InputBar'

function Toast({ toast }) {
  if (!toast) return null
  return <div className={`toast ${toast.type}`}>{toast.text}</div>
}

function formatSessionDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString()
}

function formatTagList(value) {
  if (!value) return []
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function createLocalSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `lecture-${Date.now()}`
}

export default function App() {
  const [sessions, setSessions]         = useState([])
  const [transcripts, setTranscripts]   = useState([])
  const [activeTranscriptId, setActiveTranscriptId] = useState(null)
  const [activeId, setActiveId]         = useState(null) // session_id string
  const [messages, setMessages]         = useState([])   // { role, content, sources? }
  const [loading, setLoading]           = useState(false)
  const [reprocessingId, setReprocessingId] = useState(null)
  const [toast, setToast]               = useState(null)

  // ── Toast helper ──────────────────────────────────────────────
  const showToast = (text, type = 'success') => {
    setToast({ text, type })
    setTimeout(() => setToast(null), 3000)
  }

  // ── Load sessions list ─────────────────────────────────────────
  const loadSessions = useCallback(async () => {
    try {
      const data = await api.getSessions()
      setSessions(data)
    } catch { /* silent */ }
  }, [])

  const loadTranscripts = useCallback(async () => {
    try {
      const data = await api.getTranscripts()
      setTranscripts(data)
      setActiveTranscriptId((current) => {
        if (current && data.some((item) => item.id === current)) {
          return current
        }
        return data[0]?.id ?? null
      })
    } catch { /* silent */ }
  }, [])

  useEffect(() => { loadSessions(); loadTranscripts() }, [loadSessions, loadTranscripts])

  const activeTranscript = transcripts.find((item) => item.id === activeTranscriptId) || null

  const openTranscript = (transcriptId) => {
    setActiveTranscriptId(transcriptId)
    setActiveId(null)
    setMessages([])
  }

  const reprocessTranscript = async (e, transcriptId) => {
    e.stopPropagation()
    setReprocessingId(transcriptId)
    try {
      const res = await api.reprocessTranscript(transcriptId)
      showToast(res.message || 'Transcript reprocessed.')
      loadTranscripts()
    } catch {
      showToast('Failed to reprocess transcript.', 'error')
    } finally {
      setReprocessingId(null)
    }
  }

  // ── Open / switch session ──────────────────────────────────────
  const openSession = async (sid) => {
    setActiveId(sid)
    setLoading(true)
    try {
      const history = await api.getHistory(sid)
      setMessages(history.map(m => ({ role: m.role, content: m.content })))
    } catch {
      setMessages([])
    } finally { setLoading(false) }
  }

  // ── New session ────────────────────────────────────────────────
  const newSession = () => {
    const sid = createLocalSessionId()
    const fresh = { id: Date.now(), session_id: sid, created_at: new Date().toISOString(), messages: [] }
    setSessions(prev => [fresh, ...prev])
    setActiveId(sid)
    setMessages([])
  }

  // ── Send message ───────────────────────────────────────────────
  const sendMessage = async (text) => {
    if (!activeTranscriptId) {
      showToast('Select a transcript session first.', 'error')
      return
    }

    let sid = activeId
    if (!sid) {
      sid = createLocalSessionId()
      const fresh = { id: Date.now(), session_id: sid, created_at: new Date().toISOString(), messages: [] }
      setSessions(prev => [fresh, ...prev])
      setActiveId(sid)
      setMessages([])
    }

    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    try {
      const res = await api.chat(sid, text, activeTranscriptId)
      const botMsg = { role: 'assistant', content: res.answer, sources: res.sources }
      setMessages(prev => [...prev, botMsg])
    } catch {
      showToast('Failed to get response.', 'error')
    } finally { setLoading(false) }
  }

  // ── Delete local session state ─────────────────────────────────
  const deleteSession = (e, sid) => {
    e.stopPropagation()
    setSessions(prev => prev.filter(s => s.session_id !== sid))
    if (activeId === sid) { setActiveId(null); setMessages([]) }
    showToast('Local session removed.')
  }

  const fmtId = (sid) => sid.slice(0, 8) + '…'

  return (
    <div className="app-shell">

      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="logo-icon">🤖</div>
            <div>
              <h1>Future X</h1>
              <p>RAG Chatbot</p>
            </div>
          </div>
          <button className="btn-new-chat" onClick={newSession}>
            ＋ New Chat
          </button>
        </div>

        <UploadPanel activeSessionId={activeId} onUploaded={() => {
          showToast('Transcript indexed!')
          loadTranscripts()
        }} />

        <div className="session-list transcript-list">
          <h3>Transcript Sessions</h3>
          {transcripts.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '0 8px' }}>
              No transcript sessions uploaded yet
            </p>
          )}
          {transcripts.map((item) => (
            <div
              key={item.id}
              className={`session-item${activeTranscriptId === item.id ? ' active' : ''}`}
              onClick={() => openTranscript(item.id)}
            >
              <div className="session-copy">
                <span className="session-label">
                  🎓 {item.session_name} · {item.source_name}
                </span>
                {item.metadata_entry?.course_name && (
                  <span className="session-subtitle">{item.metadata_entry.course_name}</span>
                )}
                {(item.metadata_entry?.instructor_name || item.metadata_entry?.session_date) && (
                  <span className="session-subtitle muted">
                    {[item.metadata_entry?.instructor_name, formatSessionDate(item.metadata_entry?.session_date)]
                      .filter(Boolean)
                      .join(' • ')}
                  </span>
                )}
                {item.metadata_entry?.tags && (
                  <div className="tag-row">
                    {formatTagList(item.metadata_entry.tags).slice(0, 3).map((tag) => (
                      <span key={tag} className="mini-tag">{tag}</span>
                    ))}
                  </div>
                )}
              </div>
              <button
                className="btn-del"
                onClick={(e) => reprocessTranscript(e, item.id)}
                disabled={reprocessingId === item.id}
                title="Reprocess transcript"
              >
                {reprocessingId === item.id ? '…' : '↻'}
              </button>
            </div>
          ))}
        </div>

        <div className="session-list">
          <h3>Sessions</h3>
          {sessions.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '0 8px' }}>
              No sessions yet
            </p>
          )}
              {sessions.map(s => (
                <div
                  key={s.session_id}
                  className={`session-item${activeId === s.session_id ? ' active' : ''}`}
                  onClick={() => openSession(s.session_id)}
                >
                  <span className="session-label">
                    💬 {fmtId(s.session_id)}
                  </span>
                  <button className="btn-del" onClick={(e) => deleteSession(e, s.session_id)}>✕</button>
                </div>
              ))}
            </div>
      </aside>

      {/* ── CHAT AREA ── */}
      <main className="chat-area">
        <div className="chat-topbar">
          <div className="chat-heading">
            <h2>{activeTranscript ? activeTranscript.session_name : 'Chat'}</h2>
            {activeTranscript?.metadata_entry?.description && (
              <p>{activeTranscript.metadata_entry.description}</p>
            )}
          </div>
          {activeTranscript && <span className="session-badge">{activeTranscript.source_name}</span>}
          {activeId && <span className="session-badge">{activeId.slice(0, 12)}…</span>}
        </div>

        {activeTranscript && (
          <div className="transcript-meta-card">
            <div className="transcript-meta-grid">
              <div className="transcript-meta-item">
                <span className="meta-label">Course</span>
                <span className="meta-value">{activeTranscript.metadata_entry?.course_name || 'Not provided'}</span>
              </div>
              <div className="transcript-meta-item">
                <span className="meta-label">Instructor</span>
                <span className="meta-value">{activeTranscript.metadata_entry?.instructor_name || 'Not provided'}</span>
              </div>
              <div className="transcript-meta-item">
                <span className="meta-label">Session Date</span>
                <span className="meta-value">{formatSessionDate(activeTranscript.metadata_entry?.session_date) || 'Not provided'}</span>
              </div>
              <div className="transcript-meta-item">
                <span className="meta-label">Indexed Chunks</span>
                <span className="meta-value">{activeTranscript.chunks_indexed}</span>
              </div>
              <div className="transcript-meta-item transcript-meta-item-wide">
                <span className="meta-label">Storage Path</span>
                <span className="meta-value mono">{activeTranscript.object_path}</span>
              </div>
              <div className="transcript-meta-item transcript-meta-item-wide">
                <span className="meta-label">Tags</span>
                <div className="tag-list">
                  {formatTagList(activeTranscript.metadata_entry?.tags).length > 0
                    ? formatTagList(activeTranscript.metadata_entry?.tags).map((tag) => (
                        <span key={tag} className="tag-pill">{tag}</span>
                      ))
                    : <span className="meta-value">No tags</span>}
                </div>
              </div>
            </div>
          </div>
        )}

        <ChatWindow 
          messages={messages} 
          loading={loading} 
          activeTranscript={activeTranscript}
        />

        <InputBar
          onSend={sendMessage}
          disabled={loading || !activeTranscriptId}
          placeholder={
            activeTranscript
              ? `Ask about ${activeTranscript.session_name}...`
              : 'Select a transcript session to start asking questions...'
          }
        />
      </main>

      <Toast toast={toast} />
    </div>
  )
}
