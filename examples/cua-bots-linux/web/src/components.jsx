import React, { useEffect } from 'react'
import { AvatarBadge, BOT_COLORS, BOT_COLOR_ORDER, EAR_ORDER, EYE_ORDER, Koala, normalizeAvatar } from './koala.jsx'
import { Icon } from './icons.jsx'
import { clock, relativeRun, timeAgo } from './api.js'

export function RichText({ text }) {
  const parts = String(text || '').split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return (
    <span className="rich-text">
      {parts.map((part, index) => {
        if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
        if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
        return <React.Fragment key={index}>{part}</React.Fragment>
      })}
    </span>
  )
}

export function MessageRow({ message, accent }) {
  if (message.role === 'system') {
    return <div className="message-system">{message.text}</div>
  }
  if (message.role === 'user') {
    return (
      <div className="message-row user">
        <div className="bubble user-bubble" style={{ background: `color-mix(in srgb, ${accent} 20%, transparent)` }}>
          <RichText text={message.text} />
        </div>
      </div>
    )
  }
  return (
    <div className="message-row">
      <div className="bubble bot-bubble"><RichText text={message.text} /></div>
    </div>
  )
}

export function ApprovalCard({ approval, bot, onDecide, onOpenComputer, onSignIn }) {
  const handoff = approval.source?.kind === 'handoff'
  const login = approval.source?.kind === 'login'
  return (
    <div className="card approval-card">
      <div className="card-kicker">
        <Icon name={handoff ? 'shield' : 'clock'} size={14} />
        <span>{handoff ? `${bot.name} needs you to do this` : `${bot.name} wants to`}</span>
      </div>
      <div className="card-title">{approval.action}</div>
      {approval.detail && <div className="card-detail">{approval.detail}</div>}
      {approval.state === 'pending' && (
        <div className="card-actions">
          {handoff && onOpenComputer && <button className="btn ghost" onClick={onOpenComputer}>Open computer</button>}
          {login && <button className="btn ghost" onClick={onSignIn}>Sign in</button>}
          <span className="spacer" />
          <button className="btn" onClick={() => onDecide(false)}>{handoff ? 'Not now' : 'Deny'}</button>
          <button className="btn primary" onClick={() => onDecide(true)}>{handoff ? 'I did it' : 'Approve'}</button>
        </div>
      )}
      {approval.state === 'approved' && <div className="card-state"><Icon name="checkCircle" size={14} /> Approved</div>}
      {approval.state === 'denied' && <div className="card-state"><Icon name="x" size={14} /> Denied</div>}
      {approval.state === 'handedOff' && <div className="card-state"><Icon name="checkCircle" size={14} /> You did it</div>}
    </div>
  )
}

export function SignInCard({ site, approval, onOpen }) {
  const approved = approval?.state === 'approved'
  return (
    <button className="signin-card" onClick={onOpen} disabled={!!approval && approval.state !== 'pending'}>
      <span className="signin-icon"><Icon name={approved ? 'shield' : 'lock'} size={18} /></span>
      <span className="signin-text">
        <span className="signin-kicker">{approved ? 'Signed in to' : 'Sign in to'}</span>
        <span className="signin-site">{site}</span>
      </span>
      {!approved && approval?.state === 'pending' && <Icon name="chevronRight" size={16} />}
    </button>
  )
}

export function ResultCard({ title, outputs, onOpen }) {
  return (
    <div className="card result-card">
      <div className="card-kicker"><Icon name="checkCircle" size={15} /><span>{title}</span></div>
      {outputs.map((path) => (
        <button key={path} className="output-row" onClick={() => onOpen(path)}>
          <Icon name={fileIcon(path)} size={16} />
          <span>{path.split('/').pop()}</span>
          <span className="spacer" />
          <Icon name="chevronRight" size={14} />
        </button>
      ))}
    </div>
  )
}

export function fileIcon(name) {
  const ext = String(name || '').split('.').pop()?.toLowerCase()
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) return 'image'
  if (['csv', 'xlsx', 'xls'].includes(ext)) return 'table'
  return 'doc'
}

export function TaskIcon({ task }) {
  if (task.state === 'inProgress') return <span className="spinner small" />
  if (task.state === 'completed') return <Icon name="checkCircle" size={16} />
  if (task.state === 'paused') return <Icon name="pauseCircle" size={16} />
  if (task.state === 'failed') return <Icon name="alertCircle" size={16} className="warn" />
  return <Icon name={task.symbol === 'clock' ? 'clock' : 'clockSmall'} size={16} />
}

export function TaskRow({ task, unread = false, onClick }) {
  return (
    <button className="task-row" onClick={onClick}>
      <span className={`task-icon ${task.state}`}><TaskIcon task={task} /></span>
      <span className="task-main">
        <span className="task-title">{task.title}</span>
        {task.subtitle && <span className="task-sub">{task.subtitle}</span>}
      </span>
      {unread && <span className="unread-dot" />}
    </button>
  )
}

export function PresenceLine({ bot, busy, lastActive }) {
  if (bot.is_paused) return <span>Paused</span>
  if (busy || bot.mood === 'thinking' || bot.mood === 'working') return <span>{bot.status}</span>
  if (bot.mood === 'needsApproval') return <span>Waiting for you</span>
  if (!lastActive) return <span>{bot.status}</span>
  return <span>Active {timeAgo(lastActive)}</span>
}

export function Modal({ title, subtitle, onClose, children, footer, width = 520 }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="modal" style={{ width }} role="dialog" aria-modal="true">
        <div className="modal-head">
          <div>
            <div className="modal-title">{title}</div>
            {subtitle && <div className="modal-subtitle">{subtitle}</div>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" size={16} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

const BEHAVIORS = [
  { value: 'allow', title: 'Take action without asking', blurb: 'can do this without asking.' },
  { value: 'pre-approved', title: 'Take action when you say so', blurb: 'goes ahead only when you asked for it yourself.' },
  { value: 'ask', title: 'Ask before taking action', blurb: 'asks for your approval first.' },
  { value: 'hand-off', title: 'Hand off to you', blurb: 'asks you to do it, and never does it on its own.' },
]

export function RuleForm({ action, setAction, behavior, setBehavior, botName }) {
  return (
    <div className="rule-form">
      <label className="field">
        <span className="field-label">When {botName} wants to</span>
        <textarea rows={3} value={action} onChange={(event) => setAction(event.target.value)}
                  placeholder="Share anything about the surprise party" />
      </label>
      <div className="field">
        <span className="field-label">{botName} should</span>
        <div className="behavior-list">
          {BEHAVIORS.map((item) => (
            <button key={item.value} className={`behavior ${behavior === item.value ? 'selected' : ''}`}
                    onClick={() => setBehavior(item.value)}>
              <span>
                <span className="behavior-title">{item.title}</span>
                <span className="behavior-sub">{botName} {item.blurb}</span>
              </span>
              <Icon name={behavior === item.value ? 'checkCircle' : 'circleDashed'} size={18} />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export function AvatarPicker({ avatar, setAvatar, name }) {
  return (
    <div className="avatar-picker">
      <div className="picker-section">
        <div className="field-label">Color</div>
        <div className="color-row">
          {BOT_COLOR_ORDER.map((color) => (
            <button key={color} className={`color-dot ${avatar.color === color ? 'selected' : ''}`}
                    style={{ background: BOT_COLORS[color].face }} onClick={() => setAvatar({ ...avatar, color })}
                    title={BOT_COLORS[color].name} aria-label={BOT_COLORS[color].name} />
          ))}
        </div>
      </div>
      <div className="picker-section">
        <div className="field-label">Eyes</div>
        <div className="eye-grid">
          {EYE_ORDER.map((eyes) => (
            <button key={eyes} className={`eye-option ${avatar.eyes === eyes ? 'selected' : ''}`}
                    onClick={() => setAvatar({ ...avatar, eyes })}>
              <Koala avatar={{ ...avatar, eyes }} mood="idle" size={46} animated={false} />
              <span>{eyes}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="picker-section">
        <div className="field-label">Ears</div>
        <div className="ear-row">
          {EAR_ORDER.map((ears) => (
            <button key={ears} className={`eye-option ear-option ${avatar.ears === ears ? 'selected' : ''}`}
                    onClick={() => setAvatar({ ...avatar, ears })}>
              <Koala avatar={{ ...avatar, ears }} mood="idle" size={46} animated={false} />
              <span>{ears}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export function BotAvatar({ bot, size = 22, editable = false, onClick }) {
  return <AvatarBadge avatar={normalizeAvatar(bot.avatar)} mood={bot.mood} size={size} editable={editable} onClick={onClick} />
}

export function StatusDot({ color = 'green' }) {
  return <span className={`status-dot ${color}`} />
}

export function formatWhen(iso) {
  if (!iso) return ''
  return relativeRun(iso)
}
