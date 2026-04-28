import { useEffect, useRef } from 'react'

const SEND_ICON = '➤'
const BOT_ICON  = '🤖'
const USER_ICON = '👤'

function TypingDots() {
  return (
    <div className="typing-indicator">
      <span /><span /><span />
    </div>
  )
}

function Bubble({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`msg-row ${isUser ? 'user' : 'bot'}`}>
      <div className={`avatar ${isUser ? 'user' : 'bot'}`}>
        {isUser ? USER_ICON : BOT_ICON}
      </div>
      <div className={`bubble ${isUser ? 'user' : 'bot'}`}>
        {msg.content}
        {msg.sources && msg.sources.length > 0 && (
          <div className="sources">
            📌 Sources: {msg.sources.map(s => <span key={s}>{s}</span>)}
          </div>
        )}
      </div>
    </div>
  )
}

export function ChatWindow({
  messages,
  loading,
  onRequestMentor,
  mentorRequested,
  activeTranscript,
}) {
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  if (!messages.length && !loading) {
    return (
      <div className="messages-wrap">
        <div className="empty-state">
          <span className="empty-icon">💬</span>
          <p>
            {activeTranscript
              ? `Ask anything about ${activeTranscript.session_name} and this chat will stay inside that transcript.`
              : 'Select a transcript session, then ask questions about that lecture.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="messages-wrap">
      {messages.map((m, i) => <Bubble key={i} msg={m} />)}
      
      {loading && (
        <div className="msg-row bot">
          <div className="avatar bot">{BOT_ICON}</div>
          <div className="bubble bot"><TypingDots /></div>
        </div>
      )}

      {mentorRequested ? (
        <div className="mentor-notice">
          <span className="mentor-icon">👨‍🏫</span>
          <div className="mentor-text">
            <h4>Mentor Requested</h4>
            <p>A mentor has been notified and will join this session shortly to help you with your doubts.</p>
          </div>
        </div>
      ) : (
        messages.length > 0 && !loading && (
          <div className="satisfaction-check">
            <p>Still have doubts? If the AI couldn't solve it, you can connect with a mentor.</p>
            <button className="btn-mentor" onClick={onRequestMentor}>
              Connect to Mentor
            </button>
          </div>
        )
      )}

      <div ref={bottomRef} style={{ height: 1 }} />
    </div>
  )
}
