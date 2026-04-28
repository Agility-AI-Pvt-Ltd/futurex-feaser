import { useState, useRef } from 'react'
import { api } from '../api'

const SUPPORTED_EXTENSIONS = ['.txt', '.vtt']

function isSupportedTranscript(fileName) {
  return SUPPORTED_EXTENSIONS.some((extension) =>
    fileName.toLowerCase().endsWith(extension)
  )
}

function sourceNameFromFile(fileName) {
  return fileName.replace(/\.(txt|vtt)$/i, '')
}

export function UploadPanel({ activeSessionId, onUploaded }) {
  const [file, setFile] = useState(null)
  const [sessionName, setSessionName] = useState('')
  const [sourceName, setSourceName] = useState('')
  const [courseName, setCourseName] = useState('')
  const [instructorName, setInstructorName] = useState('')
  const [sessionDate, setSessionDate] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [status, setStatus] = useState(null) // { type, text }
  const [loading, setLoading] = useState(false)
  const [drag, setDrag] = useState(false)
  const inputRef = useRef()

  const pick = (f) => {
    if (f && isSupportedTranscript(f.name)) {
      setFile(f)
      if (!sourceName.trim()) {
        setSourceName(sourceNameFromFile(f.name))
      }
      setStatus(null)
    } else {
      setFile(null)
      setStatus({ type: 'error', text: 'Only .txt and .vtt files are supported.' })
    }
  }

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false)
    pick(e.dataTransfer.files[0])
  }

  const upload = async () => {
    if (!file || !sessionName.trim()) {
      setStatus({ type: 'error', text: 'Session name and transcript file are required.' })
      return
    }
    setLoading(true); setStatus(null)
    try {
      const res = await api.uploadTranscript(file, {
        sessionName: sessionName.trim(),
        sourceName: sourceName.trim() || sourceNameFromFile(file.name),
        chatSessionId: activeSessionId,
        courseName: courseName.trim(),
        instructorName: instructorName.trim(),
        sessionDate,
        description: description.trim(),
        tags: tags.trim(),
      })
      if (res.chunks_indexed !== undefined) {
        setStatus({
          type: 'success',
          text: `Uploaded ${res.source_name} and indexed ${res.chunks_indexed} chunks`,
        })
        onUploaded && onUploaded()
        setFile(null)
        setSessionName('')
        setSourceName('')
        setCourseName('')
        setInstructorName('')
        setSessionDate('')
        setDescription('')
        setTags('')
      } else {
        setStatus({ type: 'error', text: res.detail || 'Upload failed.' })
      }
    } catch {
      setStatus({ type: 'error', text: 'Server error.' })
    } finally { setLoading(false) }
  }

  return (
    <div className="upload-panel">
      <h3>📄 Transcript</h3>
      <input
        className="input"
        value={sessionName}
        onChange={(e) => setSessionName(e.target.value)}
        placeholder="Session folder, e.g. session1"
      />
      <input
        className="input"
        value={sourceName}
        onChange={(e) => setSourceName(e.target.value)}
        placeholder="Transcript title"
      />
      <input
        className="input"
        value={courseName}
        onChange={(e) => setCourseName(e.target.value)}
        placeholder="Course or module name"
      />
      <input
        className="input"
        value={instructorName}
        onChange={(e) => setInstructorName(e.target.value)}
        placeholder="Instructor or speaker"
      />
      <input
        className="input"
        type="date"
        value={sessionDate}
        onChange={(e) => setSessionDate(e.target.value)}
      />
      <textarea
        className="input"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Short description for this lecture session"
        rows={3}
      />
      <input
        className="input"
        value={tags}
        onChange={(e) => setTags(e.target.value)}
        placeholder="Tags, comma separated"
      />
      <div
        className={`drop-zone${drag ? ' drag-over' : ''}`}
        onClick={() => inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <input ref={inputRef} type="file" accept=".txt,.vtt,text/plain,text/vtt"
          onChange={(e) => pick(e.target.files[0])} />
        <span className="drop-icon">📂</span>
        <span>{file ? file.name : 'Drop .txt or .vtt, or click to browse'}</span>
      </div>
      {file && <div className="upload-filename">{file.name}</div>}
      <button className="btn-upload" onClick={upload} disabled={!file || !sessionName.trim() || loading}>
        {loading ? 'Indexing…' : 'Upload & Index'}
      </button>
      {status && <div className={`upload-status ${status.type}`}>{status.text}</div>}
    </div>
  )
}
