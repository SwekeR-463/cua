import React, { useEffect, useRef, useState } from 'react'
import { AvatarBadge, Koala, normalizeAvatar, BOT_COLORS, defaultColorFor } from './koala.jsx'
import { AvatarPicker, BotAvatar, ApprovalCard, MessageRow, PresenceLine, ResultCard, SignInCard, TaskRow, fileIcon } from './components.jsx'
import { Icon } from './icons.jsx'
import { api, day, relativeRun, timeAgo } from './api.js'

function unreadFor(state, botId) {
  const approvals = state.approvals?.some((a) => a.bot_id === botId && a.state === 'pending')
  const notices = state.notifications?.some((n) => n.bot_id === botId && !n.read)
  return approvals || notices
}

export function Sidebar({ state, route, setRoute, onNewBot }) {
  const pending = state.approvals?.filter((a) => a.state === 'pending').length || 0
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark"><Koala avatar={{ color: 'cloud' }} size={24} animated={false} /></span>
        <span className="brand-name">Cua Bots</span>
        <span className="brand-tag">Linux</span>
      </div>
      <nav className="nav">
        <button className={`nav-row ${route.kind === 'new' ? 'active' : ''}`} onClick={onNewBot}>
          <Icon name="plusBubble" size={17} /><span>New bot</span>
        </button>
        {state.bots.map((bot) => (
          <button key={bot.id} className={`nav-row bot-nav ${route.kind === 'bot' && route.id === bot.id ? 'active' : ''}`}
                  onClick={() => setRoute({ kind: 'bot', id: bot.id })}>
            <BotAvatar bot={bot} size={22} />
            <span className="nav-label">{bot.name}</span>
            {bot.is_paused ? <Icon name="pauseCircle" size={14} className="muted" />
              : unreadFor(state, bot.id) ? <span className="unread-dot" /> : null}
          </button>
        ))}
      </nav>
      <div className="nav-section">
        <div className="nav-section-title">Work</div>
        <button className={`nav-row ${route.kind === 'scheduled' ? 'active' : ''}`} onClick={() => setRoute({ kind: 'scheduled' })}>
          <Icon name="clock" size={17} /><span> Scheduled</span>
        </button>
        <button className={`nav-row ${route.kind === 'approvals' ? 'active' : ''}`} onClick={() => setRoute({ kind: 'approvals' })}>
          <Icon name="shield" size={17} /><span> Approvals</span>
          {pending > 0 && <span className="nav-count">{pending}</span>}
        </button>
        <button className={`nav-row ${route.kind === 'outputs' ? 'active' : ''}`} onClick={() => setRoute({ kind: 'outputs' })}>
          <Icon name="tray" size={17} /><span> Outputs</span>
        </button>
      </div>
      <div className="sidebar-foot">
        <span className={`status-dot ${state.engine_error ? 'red' : 'green'}`} />
        <span className="foot-label">{state.engine_error ? 'Cua offline' : 'Spaces on this computer'}</span>
        <span className="spacer" />
        <span className="foot-model" title={state.model?.label}>{state.model?.demo ? 'demo' : 'local'}</span>
      </div>
    </aside>
  )
}

export function NewBotView({ draft, setDraft, onCreate, engineError }) {
  const name = draft.name
  const displayName = name.trim() || 'your bot'
  const step = draft.step
  const avatar = normalizeAvatar(draft.avatar)
  const setName = (value) => {
    const next = { ...draft, name: value }
    if (!draft.customized) next.avatar = { ...draft.avatar, color: defaultColorFor(value) }
    setDraft(next)
  }
  const setAvatar = (next) => setDraft({ ...draft, avatar: next, customized: true })
  return (
    <div className="newbot">
      <div className="newbot-inner">
        <div className="newbot-avatar">
          <Koala avatar={avatar} mood={step === 2 ? 'done' : 'idle'} size={128} />
        </div>
        {step === 0 && (
          <div className="newbot-step">
            <h1>Meet your bot</h1>
            <p className="lead">A bot works on its own computer, keeps going while you're away, remembers what matters to you, and checks in when something needs your approval.</p>
            <input className="name-input" autoFocus value={name} placeholder="What should we call it?"
                   onChange={(event) => setName(event.target.value)}
                   onKeyDown={(event) => { if (event.key === 'Enter' && name.trim()) setDraft({ ...draft, step: 1 }) }} />
          </div>
        )}
        {step === 1 && (
          <div className="newbot-step">
            <h1>Make {displayName} yours</h1>
            <AvatarPicker avatar={avatar} setAvatar={setAvatar} name={displayName} />
          </div>
        )}
        {step === 2 && (
          <div className="newbot-step">
            <h1>Where it lives</h1>
            <div className="form-card">
              <div className="field-label">Its computer</div>
              <div className="segmented">
                <button className={draft.placement === 'local' ? 'selected' : ''}
                        onClick={() => setDraft({ ...draft, placement: 'local' })}>This computer</button>
                <button disabled title="Cua Cloud has ended">Cua Cloud</button>
              </div>
              <div className="field-label" style={{ marginTop: 18 }}>Agent</div>
              <div className="agent-list">
                {[
                  ['hermes', 'Hermes', 'A persistent assistant with its own memory'],
                  ['openclaw', 'OpenClaw', 'A persistent assistant with standing orders'],
                  ['openai-codex', 'Codex', 'A coding agent'],
                  ['claude-code', 'Claude Code', 'A coding agent'],
                ].map(([value, title, blurb]) => (
                  <button key={value} className={`agent-option ${draft.harness === value ? 'selected' : ''}`}
                          onClick={() => setDraft({ ...draft, harness: value })}>
                    <span><span className="agent-title">{title}</span><span className="agent-sub">{blurb}</span></span>
                    <Icon name={draft.harness === value ? 'checkCircle' : 'circleDashed'} size={18} />
                  </button>
                ))}
              </div>
              <div className="memory-line">
                <Icon name="brain" size={16} />
                <span>Memory</span>
                <span className="spacer" />
                <code>agents/{name.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'bot'}</code>
              </div>
              {engineError && <div className="inline-error">{engineError}</div>}
            </div>
          </div>
        )}
        <div className="newbot-foot">
          {step > 0 ? <button className="btn" onClick={() => setDraft({ ...draft, step: step - 1 })}>Back</button> : <span />}
          <span className="dots">{[0, 1, 2].map((i) => <span key={i} className={i === step ? 'on' : ''} />)}</span>
          {step < 2 ? (
            <button className="btn primary" disabled={step === 0 && !name.trim()}
                    onClick={() => setDraft({ ...draft, step: step + 1 })}>Continue</button>
          ) : (
            <button className="btn primary" disabled={!name.trim()} onClick={onCreate}>Create {displayName}</button>
          )}
        </div>
      </div>
    </div>
  )
}

function dayLabel(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function ChatView({ bot, state, onSend, onAttach, onDecide, onOpenComputer, onOpenSignIn, onOpenOutput, onTogglePause }) {
  const messages = state.messages?.[bot.id] || []
  const busy = state.busy?.includes(bot.id)
  const setup = state.setup_phase?.[bot.id]
  const [text, setText] = useState('')
  const scrollRef = useRef(null)
  const fileRef = useRef(null)
  const inputRef = useRef(null)
  const accent = BOT_COLORS[normalizeAvatar(bot.avatar).color].accent

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages.length, busy, setup, bot.id])

  const send = () => {
    const value = text.trim()
    if (!value) return
    setText('')
    onSend(value)
  }
  const attach = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) await onAttach(file)
  }

  return (
    <div className="chat">
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-head">
          <AvatarBadge avatar={bot.avatar} mood={bot.mood} size={64} />
          <div className="chat-name">{bot.name}</div>
          <div className="chat-presence"><PresenceLine bot={bot} busy={busy} lastActive={state.messages?.[bot.id]?.slice().reverse().find((m) => m.role === 'bot')?.date} /></div>
        </div>
        <div className="messages">
          {messages.map((message, index) => {
            const previous = messages[index - 1]
            const showDay = !previous || new Date(previous.date).toDateString() !== new Date(message.date).toDateString()
            return (
              <React.Fragment key={message.id}>
                {showDay && <div className="day-sep">{dayLabel(message.date)}</div>}
                <ChatItem message={message} bot={bot} state={state} accent={accent}
                          onDecide={onDecide} onOpenComputer={onOpenComputer}
                          onOpenSignIn={onOpenSignIn} onOpenOutput={onOpenOutput} />
              </React.Fragment>
            )
          })}
          {busy && <div className="typing"><span className="spinner small" />{bot.status}</div>}
          {setup && <div className="typing"><span className="spinner small" />{setup}</div>}
          {messages.length <= 2 && <Suggestions onPick={(value) => { setText(value); inputRef.current?.focus() }} />}
        </div>
      </div>
      {bot.is_paused && (
        <button className="paused-bar" onClick={onTogglePause} title="Resume">
          <Icon name="pauseCircle" size={15} /> Paused · Resume from the toolbar
        </button>
      )}
      <div className="composer-wrap">
        <div className="composer">
          <button className="icon-btn" onClick={() => fileRef.current?.click()} title={`Hand ${bot.name} a file`}><Icon name="plus" size={18} /></button>
          <input ref={fileRef} type="file" hidden onChange={attach} />
          <textarea ref={inputRef} rows={1} value={text} placeholder={`Message ${bot.name}`}
                    onChange={(event) => setText(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send() }
                    }} />
          <button className="send-btn" onClick={send} disabled={!text.trim()} title="Send"><Icon name="arrowUp" size={18} /></button>
        </div>
      </div>
    </div>
  )
}

function ChatItem({ message, bot, state, accent, onDecide, onOpenComputer, onOpenSignIn, onOpenOutput }) {
  const kind = message.kind || { type: 'text' }
  if (kind.type === 'approval') {
    const approval = state.approvals?.find((a) => a.id === kind.id)
    if (!approval) return null
    return <ApprovalCard approval={approval} bot={bot} onDecide={(approve) => onDecide(approval, approve)}
                         onOpenComputer={onOpenComputer} onSignIn={() => onOpenSignIn(approval)} />
  }
  if (kind.type === 'login') {
    const approval = state.approvals?.find((a) => a.id === kind.approval_id)
    return <SignInCard site={kind.site} approval={approval} onOpen={() => onOpenSignIn(approval)} />
  }
  if (kind.type === 'result') {
    return <ResultCard title={kind.title} outputs={kind.outputs} onOpen={onOpenOutput} />
  }
  if (kind.type === 'notice') {
    return <div className="message-system">{message.text}</div>
  }
  return <MessageRow message={message} accent={accent} />
}

function Suggestions({ onPick }) {
  const items = [
    'Research standing desks and write me a short summary',
    'Every morning at 9, summarize what changed on news.ycombinator.com',
    'Log me into github.com and check my notifications',
  ]
  return (
    <div className="suggestions">
      <div className="field-label">Try</div>
      {items.map((item) => <button key={item} className="suggestion" onClick={() => onPick(item)}>{item}</button>)}
    </div>
  )
}

export function ComputerPane({ bot, engineError, onClose, onInterrupt }) {
  const [src, setSrc] = useState('')
  const [error, setError] = useState('')
  const [control, setControl] = useState(false)
  const [pointer, setPointer] = useState(null)
  const [dims, setDims] = useState({ width: 1280, height: 800 })
  const imgRef = useRef(null)
  const accent = BOT_COLORS[normalizeAvatar(bot.avatar).color].accent

  useEffect(() => {
    let cancelled = false
    let timer
    const load = async () => {
      if (cancelled) return
      try {
        const response = await fetch(`/api/bots/${encodeURIComponent(bot.id)}/screenshot?t=${Date.now()}`)
        if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'No screen')
        const blob = await response.blob()
        const url = URL.createObjectURL(blob)
        if (cancelled) { URL.revokeObjectURL(url); return }
        setSrc((old) => { if (old) URL.revokeObjectURL(old); return url })
        const width = Number(response.headers.get('x-screen-width')) || dims.width
        const height = Number(response.headers.get('x-screen-height')) || dims.height
        setDims({ width, height })
        setError('')
      } catch (err) {
        if (!cancelled) setError(err.message || 'Not reachable')
      }
      if (!cancelled) timer = setTimeout(load, 750)
    }
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
      setSrc((old) => { if (old) URL.revokeObjectURL(old); return '' })
    }
  }, [bot.id, bot.space_id])

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const point = await api.get(`/api/bots/${encodeURIComponent(bot.id)}/pointer`)
        if (!cancelled) setPointer(point.x == null ? null : point)
      } catch { /* ignore */ }
      if (!cancelled) setTimeout(tick, 400)
    }
    tick()
    return () => { cancelled = true }
  }, [bot.id])

  const send = (payload) => api.post(`/api/bots/${encodeURIComponent(bot.id)}/input`, payload).catch(() => {})
  const coords = (event) => {
    const img = imgRef.current
    if (!img) return { x: 0, y: 0 }
    const rect = img.getBoundingClientRect()
    return {
      x: Math.round(((event.clientX - rect.left) / rect.width) * dims.width),
      y: Math.round(((event.clientY - rect.top) / rect.height) * dims.height),
    }
  }
  const takeOver = () => {
    const next = !control
    setControl(next)
    if (next) {
      api.post(`/api/bots/${encodeURIComponent(bot.id)}/interrupt`).catch(() => {})
      onInterrupt?.()
    }
  }

  return (
    <div className="computer-pane">
      <div className="pane-head">
        <Icon name="desktop" size={17} className="muted" />
        <span className="pane-title">{bot.computer_title}</span>
        {bot.space_id && <code className="space-id">{bot.space_id}</code>}
        <span className="spacer" />
        <button className="icon-btn" onClick={onClose} title="Close"><Icon name="x" size={16} /></button>
      </div>
      <div className="computer-body">
        <div className="computer-frame" style={{ '--frame': accent, aspectRatio: `${dims.width} / ${dims.height}` }}>
          <div className={`screen-wrap ${control ? 'controlling' : ''}`} tabIndex={control ? 0 : -1}
               onClick={(event) => { if (control) { const p = coords(event); send({ action: 'click', ...p }); event.currentTarget.focus() } }}
               onDoubleClick={(event) => { if (control) { const p = coords(event); send({ action: 'double_click', ...p }) } }}
               onWheel={(event) => { if (control) { event.preventDefault(); send({ action: 'scroll', dx: 0, dy: event.deltaY > 0 ? -3 : 3 }) } }}
               onKeyDown={(event) => {
                 if (!control) return
                 if (event.key.length === 1 && !event.metaKey && !event.ctrlKey) { send({ action: 'type', text: event.key }); event.preventDefault(); return }
                 if (event.key === 'Enter' || event.key === 'Backspace' || event.key === 'Tab' || event.key === 'Escape' || event.key.startsWith('Arrow')) {
                   send({ action: 'key', key: event.key }); event.preventDefault()
                 }
               }}>
            {src ? <img ref={imgRef} src={src} alt={`${bot.computer_title} screen`} draggable={false} /> : (
              <div className="screen-empty">
                <span className="spinner" />
                <span>{error || `Connecting to ${bot.computer_title}`}</span>
              </div>
            )}
            {!control && pointer && src && (
              <span className="bot-pointer" style={{ left: `${(pointer.x / dims.width) * 100}%`, top: `${(pointer.y / dims.height) * 100}%` }}>
                <Koala avatar={bot.avatar} mood={bot.mood} size={30} />
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="control-pill">
        <span>{control ? 'You have control' : `${bot.name} has control`}</span>
        <button className="btn primary small" onClick={takeOver}>{control ? 'Return control' : 'Take over'}</button>
      </div>
      {engineError && <div className="pane-error">{engineError}</div>}
    </div>
  )
}

export function ProfilePanel({ bot, state, onTogglePause, onEditAvatar, onOpenRules, onOpenMemory, onReset, onOpenComputer, onOpenOutput, onOpenSignIn, onEnableNotifications, notificationsGranted }) {
  const [showAll, setShowAll] = useState(false)
  const tasks = state.tasks?.[bot.id] || []
  const files = [] // fetched lazily below
  const [outputs, setOutputs] = useState([])
  const approvals = state.approvals?.filter((a) => a.bot_id === bot.id && a.state === 'pending') || []
  const busy = state.busy?.includes(bot.id)
  const lastActive = state.messages?.[bot.id]?.slice().reverse().find((m) => m.role === 'bot')?.date

  useEffect(() => {
    api.get(`/api/bots/${encodeURIComponent(bot.id)}/outputs`).then((data) => setOutputs(data.files || [])).catch(() => setOutputs([]))
  }, [bot.id, tasks.length])

  const visibleTasks = showAll ? tasks : tasks.slice(0, 4)
  return (
    <aside className="profile">
      <div className="profile-identity">
        <div className="profile-menu">
          <details>
            <summary className="icon-btn" aria-label="Bot menu"><Icon name="ellipsis" size={18} /></summary>
            <div className="menu-pop">
              <button onClick={onTogglePause}>{bot.is_paused ? 'Resume' : 'Pause'}</button>
              <button onClick={onEditAvatar}>Rename and edit look…</button>
              <div className="menu-sep" />
              <button className="danger" onClick={onReset}>Reset…</button>
            </div>
          </details>
        </div>
        <AvatarBadge avatar={bot.avatar} mood={bot.mood} size={84} editable onClick={onEditAvatar} />
        <div className="profile-name">{bot.name}</div>
        <div className="profile-handle">{bot.handle}</div>
        {bot.is_paused
          ? <button className="link-btn" onClick={onTogglePause}>Paused · Click to resume</button>
          : <div className="profile-presence"><PresenceLine bot={bot} busy={busy} lastActive={lastActive} /></div>}
        <div className="profile-actions">
          <button className="circle-btn" title="Message"><Icon name="message" size={16} /></button>
          <button className="circle-btn" title="Open computer" onClick={onOpenComputer}><Icon name="desktop" size={16} /></button>
          <button className="circle-btn" title={bot.is_paused ? 'Resume' : 'Pause'} onClick={onTogglePause}><Icon name={bot.is_paused ? 'play' : 'pause'} size={16} /></button>
          <button className="circle-btn" title="Picture in picture" onClick={() => window.open(`/pip.html?bot=${encodeURIComponent(bot.id)}`, 'cua-pip', 'width=960,height=640')}><Icon name="pip" size={16} /></button>
        </div>
      </div>

      {!notificationsGranted && typeof Notification !== 'undefined' && (
        <section className="profile-section">
          <div className="section-title">Notifications</div>
          <div className="box">
            <div className="row-btn static">
              <span className="row-icon"><Icon name="bell" size={16} /></span>
              <span className="row-main"><span>Enable notifications</span><span className="row-sub">Approvals and finished work</span></span>
              <button className="btn small" onClick={onEnableNotifications}>Allow</button>
            </div>
          </div>
        </section>
      )}

      {approvals.length > 0 && (
        <section className="profile-section">
          <div className="section-title">Waiting for you</div>
          <div className="box">
            {approvals.slice(0, 2).map((approval) => (
              <div key={approval.id} className="mini-approval">
                <span>{approval.action}</span>
                <button className="btn small" onClick={() => onOpenSignIn(approval)}>Review</button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="profile-section">
        <div className="section-title">Computers</div>
        <div className="box">
          <button className="row-btn" onClick={onOpenComputer}>
            <span className="row-icon"><Icon name="desktop" size={16} /></span>
            <span className="row-main">
              <span>{bot.computer_title}</span>
              <span className="row-sub">{bot.space_id ? (bot.is_paused ? 'Suspended' : 'Connected') : (state.setup_phase?.[bot.id] || 'Not created')}</span>
            </span>
            <span className={`status-dot ${bot.space_id ? (bot.is_paused ? 'orange' : 'green') : 'gray'}`} />
            {bot.space_id && <img className="thumb" src={`/api/bots/${encodeURIComponent(bot.id)}/screenshot?t=${Date.now()}`} alt="" />}
          </button>
          <div className="divider" />
          <div className="row-btn static">
            <span className="row-icon"><Icon name="laptop" size={16} /></span>
            <span className="row-main"><span>This computer</span><span className="row-sub">Host access is not part of the Linux port</span></span>
          </div>
        </div>
      </section>

      <section className="profile-section">
        <div className="section-title">Activity</div>
        <div className="box">
          {tasks.length === 0 && <div className="empty-note">Nothing yet. Ask {bot.name} for something, or schedule a routine.</div>}
          {visibleTasks.map((task, index) => (
            <React.Fragment key={task.id}>
              <TaskRow task={task} unread={task.state === 'completed' && task.last_run && Date.now() - new Date(task.last_run).getTime() < 600000} />
              {index < visibleTasks.length - 1 && <div className="divider" />}
            </React.Fragment>
          ))}
          {tasks.length > 4 && (
            <><div className="divider" /><button className="link-btn" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show less' : 'Show more'}</button></>
          )}
        </div>
      </section>

      <section className="profile-section">
        <div className="section-title">Outputs</div>
        <div className="box">
          {outputs.length === 0 && <div className="empty-note">Finished files land in agents/{bot.id}/outputs.</div>}
          {outputs.slice(0, 6).map((file) => (
            <button key={file.path} className="row-btn" onClick={() => onOpenOutput(file.path)}>
              <span className="row-icon"><Icon name={fileIcon(file.name)} size={16} /></span>
              <span className="row-main"><span>{file.name}</span></span>
              <Icon name="chevronRight" size={13} className="muted" />
            </button>
          ))}
        </div>
      </section>

      <section className="profile-section">
        <div className="section-title">Customize</div>
        <div className="box">
          <button className="row-btn" onClick={onOpenMemory}><span className="row-icon"><Icon name="brain" size={16} /></span><span className="row-main"><span>Memory</span><span className="row-sub">agents/{bot.id}/memory</span></span><Icon name="chevronRight" size={13} className="muted" /></button>
          <div className="divider" />
          <button className="row-btn" onClick={onOpenRules}><span className="row-icon"><Icon name="checklist" size={16} /></span><span className="row-main"><span>Custom rules</span><span className="row-sub">{(state.rules?.[bot.id] || []).length} rules</span></span><Icon name="chevronRight" size={13} className="muted" /></button>
          <div className="divider" />
          <button className="row-btn" onClick={() => onOpenSignIn(null)}><span className="row-icon"><Icon name="key" size={16} /></span><span className="row-main"><span>Saved sign-ins</span><span className="row-sub">Take over the computer to sign in</span></span></button>
          <div className="divider" />
          <div className="row-btn static"><span className="row-icon"><Icon name="cpu" size={16} /></span><span className="row-main"><span>Runs on</span><span className="row-sub">{[bot.harness, bot.placement].join(' · ')}</span></span></div>
        </div>
      </section>
    </aside>
  )
}

export function ScheduledView({ state, onRunTask, onUpdateTask, onDeleteTask, onNewRoutine }) {
  const scheduled = state.bots.flatMap((bot) => (state.tasks?.[bot.id] || []).filter((t) => t.schedule).map((task) => ({ bot, task })))
  const log = state.clock?.log || []
  return (
    <div className="page">
      <div className="page-head">
        <h1>Scheduled</h1>
        <button className="btn primary" onClick={onNewRoutine} disabled={state.bots.length === 0}><Icon name="plus" size={15} /> New routine</button>
      </div>
      <div className="page-body">
        {state.bots.map((bot) => {
          const tasks = (state.tasks?.[bot.id] || []).filter((t) => t.schedule)
          return (
            <section key={bot.id} className="list-section">
              <div className="list-head"><BotAvatar bot={bot} size={18} /><span>{bot.name}</span>{bot.is_paused && <span className="muted">Paused</span>}</div>
              <div className="box">
                {tasks.length === 0 && <div className="empty-note">No scheduled work</div>}
                {tasks.map((task) => (
                  <div key={task.id} className="scheduled-row">
                    <TaskRow task={task} />
                    <span className="scheduled-last">{task.last_run ? `Last run ${new Date(task.last_run).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}</span>
                    <label className="switch" title="Enabled">
                      <input type="checkbox" checked={task.state === 'scheduled'} disabled={bot.is_paused}
                             onChange={(event) => onUpdateTask(task, { state: event.target.checked ? 'scheduled' : 'paused' })} />
                      <span />
                    </label>
                    <button className={`icon-btn ${task.notify_on_completion ? 'on' : ''}`} title="Notify me when it finishes"
                            onClick={() => onUpdateTask(task, { notify_on_completion: !task.notify_on_completion })}><Icon name="bell" size={15} /></button>
                    <button className="icon-btn" title="Run now" onClick={() => onRunTask(task)}><Icon name="play" size={14} /></button>
                    <button className="icon-btn danger" title="Delete" onClick={() => onDeleteTask(task)}><Icon name="x" size={14} /></button>
                  </div>
                ))}
              </div>
            </section>
          )
        })}
        <section className="list-section">
          <div className="list-head">Recent firings</div>
          <div className="box">
            {log.length === 0 && <div className="empty-note">Nothing fired yet</div>}
            {log.slice(0, 8).map((entry) => (
              <div key={entry.id} className="log-row">
                <span>{entry.title}</span><span className="muted">{entry.summary}</span>
                <span className="muted">{new Date(entry.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export function ApprovalsView({ state, onDecide, onOpenComputer, onOpenSignIn }) {
  const pending = state.approvals?.filter((a) => a.state === 'pending') || []
  return (
    <div className="page">
      <div className="page-head"><h1>Approvals</h1></div>
      <div className="page-body narrow">
        {pending.length === 0 && <div className="empty-large">Nothing is waiting for you.</div>}
        {pending.map((approval) => {
          const bot = state.bots.find((b) => b.id === approval.bot_id)
          if (!bot) return null
          return <ApprovalCard key={approval.id} approval={approval} bot={bot}
                               onDecide={(approve) => onDecide(approval, approve)}
                               onOpenComputer={() => onOpenComputer(bot)}
                               onSignIn={() => onOpenSignIn(approval)} />
        })}
      </div>
    </div>
  )
}

export function OutputsView({ state, onOpenOutput }) {
  const [files, setFiles] = useState({})
  useEffect(() => { let cancelled = false; Promise.all(state.bots.map((bot) => api.get(`/api/bots/${encodeURIComponent(bot.id)}/outputs`).then((data) => [bot.id, data.files || []]).catch(() => [bot.id, []]))).then((entries) => { if (!cancelled) setFiles(Object.fromEntries(entries)) }); return () => { cancelled = true } }, [state.bots.length])
  return (
    <div className="page">
      <div className="page-head"><h1>Outputs</h1></div>
      <div className="page-body">
        {state.bots.map((bot) => (
          <section key={bot.id} className="list-section">
            <div className="list-head"><BotAvatar bot={bot} size={18} /><span>{bot.name}</span></div>
            <div className="box">
              {(files[bot.id] || []).length === 0 && <div className="empty-note">Nothing yet</div>}
              {(files[bot.id] || []).map((file) => (
                <button key={file.path} className="row-btn" onClick={() => onOpenOutput(file.path)}>
                  <span className="row-icon"><Icon name={fileIcon(file.name)} size={16} /></span>
                  <span className="row-main"><span>{file.name}</span></span>
                  <span className="muted small-text">{file.modified ? new Date(file.modified).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : ''}</span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
