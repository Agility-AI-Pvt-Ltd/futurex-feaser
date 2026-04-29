const BASE = '/api'

export const api = {
  chat: (session_id, message, transcriptId) =>
    fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id, message, transcript_id: transcriptId ?? null }),
    }).then(r => r.json()),

  getHistory: (session_id) =>
    fetch(`${BASE}/history/${session_id}`).then(r => r.json()),

  getSessions: () =>
    fetch(`${BASE}/sessions`).then(r => r.json()),

  uploadTranscript: (
    file,
    {
      sourceName,
      sessionName,
      chatSessionId,
      courseName,
      instructorName,
      sessionDate,
      description,
      tags,
    } = {}
  ) => {
    const form = new FormData()
    form.append('file', file)
    if (sessionName) form.append('session_name', sessionName)
    if (sourceName) form.append('source_name', sourceName)
    if (chatSessionId) form.append('chat_session_id', chatSessionId)
    if (courseName) form.append('course_name', courseName)
    if (instructorName) form.append('instructor_name', instructorName)
    if (sessionDate) form.append('session_date', sessionDate)
    if (description) form.append('description', description)
    if (tags) form.append('tags', tags)
    return fetch(`${BASE}/upload`, { method: 'POST', body: form }).then(r => r.json())
  },

  getTranscripts: () =>
    fetch(`${BASE}/transcripts`).then(r => r.json()),

  reprocessTranscript: (transcriptId) =>
    fetch(`${BASE}/transcripts/${transcriptId}/reprocess`, {
      method: 'POST',
    }).then(r => r.json()),
}
