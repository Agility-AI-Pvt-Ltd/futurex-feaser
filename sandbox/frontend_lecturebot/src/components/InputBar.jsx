import { useRef, useState } from 'react'

export function InputBar({ onSend, disabled, placeholder }) {
  const [text, setText] = useState('')
  const ref = useRef()

  const send = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    ref.current.style.height = 'auto'
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const autoResize = (e) => {
    setText(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
  }

  return (
    <div className="input-bar">
      <div className="input-row">
        <textarea
          ref={ref}
          rows={1}
          placeholder={placeholder || "Ask something about the transcript…"}
          value={text}
          onChange={autoResize}
          onKeyDown={onKey}
          disabled={disabled}
        />
        <button className="btn-send" onClick={send} disabled={disabled || !text.trim()}>
          ➤
        </button>
      </div>
      <p className="hint">Enter to send · Shift+Enter for new line</p>
    </div>
  )
}
