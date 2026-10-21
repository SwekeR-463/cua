import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api, connect } from './api.js'
import { Icon } from './icons.jsx'
import { AvatarPicker, BotAvatar, Modal, RuleForm } from './components.jsx'
import { BOT_COLORS, Koala, defaultColorFor, normalizeAvatar } from './koala.jsx'
import {
  ApprovalsView, ChatView, ComputerPane, NewBotView, OutputsView, ProfilePanel,
  ScheduledView, Sidebar,
} from './views.jsx'

const EMPTY_DRAFT = {
  step: 0,
  name: '',
  avatar: { color: 'sky', eyes: 'star', ears: 'scalloped' },
  harness: 'hermes',
  placement: 'local',
  customized: false,
}

function agentName(name) {
  return (name.toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/-+/g, '-')
    .replace(/^[-._]+|[-._]+$/g, '').slice(0, 63)) || 'bot'
}

function splitPath(path) {
  const parts = String(path).split('/')
  return { name: parts[parts.length - 1], dir: parts.slice(0, -1).join('/') }
}

function Toast({ toast, onOpen }) {
  if (!toast) return null
  return (
    <button className="toast" onClick={onOpen}>
      <span className="toast-icon"><Icon name={toast.kind === 'approval' ? 'shield' : 'checkCircle'} size={18} /></span>
      <span className="toast-text">
        <span className="toast-title">{toast.title}</span>
        {toast.body && <span className="toast-body">{toast.body}</span>}
      </span>
      <Icon name="x" size={14} className="muted" />
    </button>
  )
}

function AvatarModal({ bot, onClose, onSave }) {
  const [name, setName] = useState(bot.name)
  const [avatar, setAvatar] = useState(normalizeAvatar(bot.avatar))
  return (
    <Modal title={`Edit ${bot.name}`} subtitle="Name, color, eyes and ears" onClose={onClose} width={540}
           footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={() => onSave(name.trim() || bot.name, avatar)}>Save</button></>}>
      <div className="edit-avatar-head">
        <Koala avatar={avatar} mood={bot.mood} size={92} />
        <label className="field grow">
          <span className="field-label">Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} autoFocus />
        </label>
      </div>
      <AvatarPicker avatar={avatar} setAvatar={setAvatar} name={name || bot.name} />
    </Modal>
  )
}

function RulesModal({ bot, rules: initial, onClose, onSave }) {
  const [rules, setRules] = useState(initial.map((rule) => ({ ...rule })))
  const [adding, setAdding] = useState(false)
  const [action, setAction] = useState('')
  const [behavior, setBehavior] = useState('ask')
  const update = (id, patch) => setRules((list) => list.map((rule) => rule.id === id ? { ...rule, ...patch } : rule))
  const remove = (id) => setRules((list) => list.filter((rule) => rule.id !== id || rule.locked || rule.is_built_in))
  const add = () => {
    if (!action.trim()) return
    setRules((list) => [...list, { id: crypto.randomUUID(), action: action.trim(), behavior, action_class: null, locked: false, is_built_in: false }])
    setAction(''); setBehavior('ask'); setAdding(false)
  }
  return (
    <Modal title={`Rules for ${bot.name}`} subtitle="What it may do on its own, when it must ask, and what it hands back to you."
           onClose={onClose} width={620}
           footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={() => onSave(rules)}>Save rules</button></>}>
      <div className="rules-list">
        {rules.map((rule) => (
          <div key={rule.id} className={`rule-row ${rule.locked ? 'locked' : ''}`}>
            <div className="rule-main">
              <div className="rule-action">{rule.action}{rule.locked && <span className="lock-chip">Locked</span>}</div>
              <div className="rule-hint">{rule.is_built_in ? 'Built-in' : 'Custom'}</div>
            </div>
            <select value={rule.behavior} disabled={rule.locked}
                    onChange={(event) => update(rule.id, { behavior: event.target.value })}>
              <option value="allow">Without asking</option>
              <option value="pre-approved">When you say so</option>
              <option value="ask">Ask first</option>
              <option value="hand-off">Hand off</option>
            </select>
            {!rule.locked && !rule.is_built_in && <button className="icon-btn danger" onClick={() => remove(rule.id)}><Icon name="x" size={14} /></button>}
          </div>
        ))}
      </div>
      {adding ? (
        <div className="rule-add">
          <RuleForm action={action} setAction={setAction} behavior={behavior} setBehavior={setBehavior} botName={bot.name} />
          <div className="row-actions"><button className="btn" onClick={() => setAdding(false)}>Cancel</button><button className="btn primary" onClick={add} disabled={!action.trim()}>Add rule</button></div>
        </div>
      ) : (
        <button className="btn ghost add-rule" onClick={() => setAdding(true)}><Icon name="plus" size={15} /> New rule</button>
      )}
    </Modal>
  )
}

function MemoryModal({ bot, onClose, onSave }) {
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    api.get(`/api/bots/${encodeURIComponent(bot.id)}/memory`)
      .then((data) => setValue(data.text || ''))
      .catch(() => setValue(''))
      .finally(() => setLoading(false))
  }, [bot.id])
  return (
    <Modal title={`${bot.name}'s memory`} subtitle={`agents/${bot.id}/memory/MEMORY.md`} onClose={onClose} width={620}
           footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={() => onSave(value)} disabled={loading}>Save memory</button></>}>
      {loading ? <div className="typing"><span className="spinner small" />Loading</div>
        : <textarea className="memory-editor" rows={16} value={value} onChange={(event) => setValue(event.target.value)} autoFocus />}
      <div className="hint">Secrets belong in the Keyvault; the Volume refuses provider keys, private keys and bearer tokens.</div>
    </Modal>
  )
}

function OutputModal({ path, onClose }) {
  const [content, setContent] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let url = null
    fetch(`/api/output?path=${encodeURIComponent(path)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not read the file')
        const type = response.headers.get('content-type') || ''
        if (type.startsWith('image/')) { const blob = await response.blob(); url = URL.createObjectURL(blob); setContent({ type: 'image', url }) }
        else setContent({ type: 'text', text: await response.text() })
      })
      .catch((err) => setError(err.message))
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [path])
  return (
    <Modal title={path.split('/').pop()} subtitle={path} onClose={onClose} width={760}
           footer={<button className="btn primary" onClick={onClose}>Done</button>}>
      {error && <div className="inline-error">{error}</div>}
      {!content && !error && <div className="typing"><span className="spinner small" />Loading</div>}
      {content?.type === 'image' && <img className="output-image" src={content.url} alt={path.split('/').pop()} />}
      {content?.type === 'text' && <pre className="output-text">{content.text}</pre>}
    </Modal>
  )
}

function SignInModal({ approval, bot, onClose, onOpenComputer, onDone }) {
  const site = approval?.source?.site || approval?.action?.replace(/^Sign in to /, '') || 'the site'
  return (
    <Modal title="Sign in without sharing the password" onClose={onClose} width={480}
           footer={<><button className="btn" onClick={onClose}>Cancel</button>{approval && <button className="btn primary" onClick={onDone}>I'm signed in</button>}</>}>
      <div className="signin-modal">
        <div className="signin-lock"><Icon name="lock" size={26} /></div>
        <p>Take over {bot?.name || 'the bot'}'s computer and sign in to <strong>{site}</strong> yourself. The bot never sees the password.</p>
        {bot && <button className="btn" onClick={onOpenComputer}><Icon name="desktop" size={15} /> Open {bot.computer_title}</button>}
        {approval && <div className="hint">When you are done, press “I'm signed in” so {bot.name} can continue.</div>}
        {!approval && <div className="hint">Saved sign-ins from the Cua Keyvault are not available in the Linux port; use the bot's computer.</div>}
      </div>
    </Modal>
  )
}

function ResetModal({ bot, onClose, onReset }) {
  return (
    <Modal title={`Reset ${bot.name}?`} onClose={onClose} width={460}
           footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn danger" onClick={onReset}>Reset</button></>}>
      <p className="modal-copy">This deletes its computer, conversation, memory and scheduled tasks. Files it made in other places stay.</p>
    </Modal>
  )
}

function RoutineModal({ state, onClose, onSave }) {
  const [botId, setBotId] = useState(state.bots[0]?.id || '')
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [kind, setKind] = useState('daily')
  const [time, setTime] = useState('09:00')
  const [weekday, setWeekday] = useState(2)
  const [minutes, setMinutes] = useState(30)
  const save = () => {
    const [hour, minute] = time.split(':').map(Number)
    const schedule = kind === 'every' ? { kind: 'every', minutes: Number(minutes) }
      : kind === 'weekly' ? { kind: 'weekly', weekday: Number(weekday), hour, minute }
      : { kind: 'daily', hour, minute }
    onSave({ bot_id: botId, title: title.trim(), prompt: prompt.trim() || title.trim(), schedule })
  }
  return (
    <Modal title="New routine" onClose={onClose} width={500}
           footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={!botId || !title.trim()}>Schedule</button></>}>
      <div className="form-stack">
        <label className="field"><span className="field-label">Bot</span>
          <select value={botId} onChange={(event) => setBotId(event.target.value)}>{state.bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}</select>
        </label>
        <label className="field"><span className="field-label">Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Morning briefing" autoFocus /></label>
        <label className="field"><span className="field-label">What to do</span><textarea rows={3} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Summarize what came in overnight" /></label>
        <div className="field-row">
          <label className="field"><span className="field-label">Repeat</span>
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="every">Every few minutes</option>
            </select>
          </label>
          {kind === 'every' ? (
            <label className="field"><span className="field-label">Every (minutes)</span><input type="number" min="5" max="720" step="5" value={minutes} onChange={(event) => setMinutes(event.target.value)} /></label>
          ) : (
            <label className="field"><span className="field-label">Time</span><input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label>
          )}
          {kind === 'weekly' && (
            <label className="field"><span className="field-label">Day</span>
              <select value={weekday} onChange={(event) => setWeekday(event.target.value)}>
                {['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map((day, index) => <option key={day} value={index + 1}>{day}</option>)}
              </select>
            </label>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default function App() {
  const [state, setState] = useState(null)
  const [route, setRoute] = useState({ kind: 'boot' })
  const [draft, setDraft] = useState(EMPTY_DRAFT)
  const [showComputer, setShowComputer] = useState(false)
  const [showProfile, setShowProfile] = useState(true)
  const [modal, setModal] = useState(null)
  const [toast, setToast] = useState(null)
  const [error, setError] = useState('')
  const [wsStatus, setWsStatus] = useState('connecting')
  const [notificationStatus, setNotificationStatus] = useState(typeof Notification !== 'undefined' ? Notification.permission : 'denied')

  const selected = useMemo(() => {
    if (!state || route.kind !== 'bot') return null
    return state.bots.find((bot) => bot.id === route.id) || null
  }, [state, route])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const botId = params.get('bot')
    const view = params.get('view')
    if (botId) setRoute({ kind: 'bot', id: botId })
    else if (view && ['scheduled', 'approvals', 'outputs', 'new'].includes(view)) setRoute({ kind: view })
    if (params.get('computer') === '1') { setShowComputer(true); setShowProfile(false) }
    api.get('/api/state').then((data) => {
      setState(data)
      setRoute((current) => {
        if (data.bots.length === 0) return { kind: 'new' }
        if (current.kind === 'boot' || (current.kind === 'bot' && !data.bots.some((bot) => bot.id === current.id))) {
          return { kind: 'bot', id: data.bots[0].id }
        }
        return current
      })
    }).catch((err) => setError(err.message))
    const disconnect = connect((message) => {
      if (message.type === 'state') {
        setState(message.state)
        setRoute((current) => {
          if (message.state.bots.length === 0) return { kind: 'new' }
          if (current.kind === 'boot') return { kind: 'bot', id: message.state.bots[0].id }
          if (current.kind === 'bot' && !message.state.bots.some((bot) => bot.id === current.id)) {
            return { kind: 'bot', id: message.state.bots[0].id }
          }
          return current
        })
      } else if (message.type === 'toast') {
        showToast(message.notification)
      }
    }, setWsStatus)
    return () => disconnect()
  }, [])

  useEffect(() => {
    if (!toast) return undefined
    const id = setTimeout(() => setToast(null), 6500)
    return () => clearTimeout(id)
  }, [toast])

  useEffect(() => {
    if (selected) api.post('/api/notifications/read', { bot_id: selected.id }).then((data) => setState(data)).catch(() => {})
  }, [selected?.id])

  const showToast = (notification) => {
    if (!notification) return
    setToast(notification)
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      try { new Notification(notification.title, { body: notification.body }) } catch { /* ignore */ }
    }
  }

  const apply = (data) => { if (data && data.bots) setState(data) }
  const refresh = () => api.get('/api/state').then(setState).catch((err) => setError(err.message))

  const createBot = async () => {
    try {
      const data = await api.post('/api/bots', { name: draft.name.trim(), avatar: draft.avatar, harness: draft.harness, placement: draft.placement })
      apply(data)
      const created = data.bots[data.bots.length - 1]
      if (created) setRoute({ kind: 'bot', id: created.id })
      setDraft(EMPTY_DRAFT)
      setShowComputer(false)
    } catch (err) { setError(err.message) }
  }

  const send = async (text) => {
    if (!selected || !text) return
    try { apply(await api.post(`/api/bots/${encodeURIComponent(selected.id)}/send`, { text })) } catch (err) { setError(err.message) }
  }

  const togglePause = async () => {
    if (!selected) return
    try { apply(await api.post(`/api/bots/${encodeURIComponent(selected.id)}/${selected.is_paused ? 'resume' : 'pause'}`)) } catch (err) { setError(err.message) }
  }

  const decide = async (approval, approve) => {
    if (approval.source?.kind === 'login' && approve) { setModal({ type: 'signin', approval }); return }
    try { apply(await api.post(`/api/approvals/${encodeURIComponent(approval.id)}`, { approve })) } catch (err) { setError(err.message) }
  }

  const attach = async (file) => {
    if (!selected) return
    try {
      apply(await api.upload(`/api/bots/${encodeURIComponent(selected.id)}/inbox`, file))
      await send(`(I put ${file.name} in your inbox.)`)
    } catch (err) { setError(err.message) }
  }

  const openOutput = async (path) => setModal({ type: 'output', path })
  const openSignIn = (approval) => setModal({ type: 'signin', approval, bot: selected || state?.bots.find((bot) => bot.id === approval?.bot_id) })

  const saveAvatar = async (name, avatar) => {
    if (!selected) return
    try {
      await api.put(`/api/bots/${encodeURIComponent(selected.id)}/name`, { name })
      apply(await api.put(`/api/bots/${encodeURIComponent(selected.id)}/avatar`, avatar))
      setModal(null)
    } catch (err) { setError(err.message) }
  }

  const saveRules = async (rules) => {
    if (!selected) return
    try { apply(await api.put(`/api/bots/${encodeURIComponent(selected.id)}/rules`, { rules })); setModal(null) } catch (err) { setError(err.message) }
  }

  const saveMemory = async (text) => {
    if (!selected) return
    try { apply(await api.put(`/api/bots/${encodeURIComponent(selected.id)}/memory`, { text })); setModal(null) } catch (err) { setError(err.message) }
  }

  const resetBot = async () => {
    if (!selected) return
    try {
      const data = await api.post(`/api/bots/${encodeURIComponent(selected.id)}/reset`)
      apply(data)
      setModal(null)
      setRoute(data.bots.length ? { kind: 'bot', id: data.bots[0].id } : { kind: 'new' })
    } catch (err) { setError(err.message) }
  }

  const updateTask = async (task, patch) => {
    try { apply(await api.patch(`/api/tasks/${encodeURIComponent(task.id)}`, patch)) } catch (err) { setError(err.message) }
  }
  const runTask = async (task) => { try { apply(await api.post(`/api/tasks/${encodeURIComponent(task.id)}/fire`)) } catch (err) { setError(err.message) } }
  const deleteTask = async (task) => { try { apply(await api.delete(`/api/tasks/${encodeURIComponent(task.id)}`)) } catch (err) { setError(err.message) } }
  const createRoutine = async (body) => {
    try { apply(await api.post(`/api/bots/${encodeURIComponent(body.bot_id)}/tasks`, { title: body.title, prompt: body.prompt, schedule: body.schedule })); setModal(null) } catch (err) { setError(err.message) }
  }

  const markAllRead = () => {
    if (!selected) return
    api.post('/api/notifications/read', { bot_id: selected.id }).then(setState).catch(() => {})
  }

  if (!state) {
    return <div className="loading-screen"><span className="spinner" />Starting Cua Bots…{error && <div className="inline-error">{error}</div>}</div>
  }

  const selectedRules = selected ? (state.rules?.[selected.id] || []) : []
  return (
    <div className="app">
      <Sidebar state={state} route={route} setRoute={(next) => { setRoute(next); setShowComputer(false) }}
               onNewBot={() => { setRoute({ kind: 'new' }); setDraft(EMPTY_DRAFT); setShowComputer(false) }} />
      <main className="main">
        {state.engine_error && <div className="banner error"><Icon name="alert" size={15} /> {state.engine_error}</div>}
        {route.kind === 'new' && <NewBotView draft={draft} setDraft={setDraft} onCreate={createBot} engineError={state.engine_error} />}
        {route.kind === 'bot' && selected && (
          <div className="detail">
            <div className="detail-toolbar">
              <div className="detail-title">
                <span>{showComputer ? selected.computer_title : selected.name}</span>
                {showComputer && selected.space_id && <code>{selected.space_id}</code>}
              </div>
              <span className="spacer" />
              <button className={`tool-btn ${showComputer ? 'on' : ''}`} onClick={() => { setShowComputer(!showComputer); if (!showComputer) setShowProfile(false) }} disabled={!selected.space_id} title={selected.computer_title}><Icon name="desktop" size={16} /><span>Computer</span></button>
              <button className="tool-btn" onClick={togglePause} title={selected.is_paused ? 'Resume' : 'Pause'}><Icon name={selected.is_paused ? 'play' : 'pause'} size={16} /><span>{selected.is_paused ? 'Resume' : 'Pause'}</span></button>
              <button className={`tool-btn ${showProfile ? 'on' : ''}`} onClick={() => setShowProfile(!showProfile)} title="Profile"><Icon name="sidebar" size={16} /><span>Profile</span></button>
            </div>
            <div className="detail-body">
              <div className="chat-wrap" style={{ maxWidth: showComputer ? 380 : 860 }}>
                <ChatView bot={selected} state={state} onSend={send} onAttach={attach}
                          onDecide={decide} onOpenComputer={() => setShowComputer(true)}
                          onOpenSignIn={openSignIn} onOpenOutput={openOutput} onTogglePause={togglePause} />
              </div>
              {showComputer && <ComputerPane bot={selected} engineError={state.engine_error}
                                            onClose={() => setShowComputer(false)} />}
              {showProfile && <ProfilePanel bot={selected} state={state} onTogglePause={togglePause}
                                            onEditAvatar={() => setModal({ type: 'avatar', bot: selected })}
                                            onOpenRules={() => setModal({ type: 'rules', bot: selected, rules: selectedRules })}
                                            onOpenMemory={() => setModal({ type: 'memory', bot: selected, text: '' })}
                                            onReset={() => setModal({ type: 'reset', bot: selected })}
                                            onOpenComputer={() => { setShowComputer(true); setShowProfile(false) }}
                                            onOpenOutput={openOutput} onOpenSignIn={openSignIn}
                                            notificationsGranted={notificationStatus === 'granted'}
                                            onEnableNotifications={async () => {
                                              try { const permission = await Notification.requestPermission(); setNotificationStatus(permission) } catch { /* ignore */ }
                                            }} />}
            </div>
          </div>
        )}
        {route.kind === 'scheduled' && <ScheduledView state={state} onRunTask={runTask} onUpdateTask={updateTask}
                                                      onDeleteTask={deleteTask} onNewRoutine={() => setModal({ type: 'routine' })} />}
        {route.kind === 'approvals' && <ApprovalsView state={state} onDecide={decide}
                                                      onOpenComputer={(bot) => { setRoute({ kind: 'bot', id: bot.id }); setShowComputer(true); setShowProfile(false) }}
                                                      onOpenSignIn={openSignIn} />}
        {route.kind === 'outputs' && <OutputsView state={state} onOpenOutput={openOutput} />}
      </main>
      <Toast toast={toast} onOpen={() => { if (toast?.bot_id) setRoute({ kind: 'bot', id: toast.bot_id }); setToast(null) }} />
      {modal?.type === 'avatar' && <AvatarModal bot={modal.bot} onClose={() => setModal(null)} onSave={saveAvatar} />}
      {modal?.type === 'rules' && <RulesModal bot={modal.bot} rules={modal.rules} onClose={() => setModal(null)} onSave={saveRules} />}
      {modal?.type === 'memory' && <MemoryModal bot={modal.bot} onClose={() => setModal(null)} onSave={saveMemory} />}
      {modal?.type === 'output' && <OutputModal path={modal.path} onClose={() => setModal(null)} />}
      {modal?.type === 'signin' && <SignInModal approval={modal.approval} bot={modal.bot || selected} onClose={() => setModal(null)}
                                                onOpenComputer={() => { setModal(null); setShowComputer(true); setShowProfile(false) }}
                                                onDone={async () => {
                                                  try { if (modal.approval) apply(await api.post(`/api/approvals/${encodeURIComponent(modal.approval.id)}/signin`)); setModal(null) } catch (err) { setError(err.message) }
                                                }} />}
      {modal?.type === 'reset' && <ResetModal bot={modal.bot} onClose={() => setModal(null)} onReset={resetBot} />}
      {modal?.type === 'routine' && <RoutineModal state={state} onClose={() => setModal(null)} onSave={createRoutine} />}
      {error && <div className="error-toast" onClick={() => setError('')}><Icon name="alert" size={15} /> {error}<Icon name="x" size={13} /></div>}
    </div>
  )
}
