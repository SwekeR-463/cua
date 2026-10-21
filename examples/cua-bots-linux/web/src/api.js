async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  let body = options.body
  if (body !== undefined && !(body instanceof FormData)) {
    headers['content-type'] = 'application/json'
    body = JSON.stringify(body)
  }
  const response = await fetch(path, { ...options, headers, body })
  const text = await response.text()
  let data = null
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }
  if (!response.ok) {
    const message = data?.detail || (typeof data === 'string' ? data : `Request failed (${response.status})`)
    throw new Error(message)
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, file) => {
    const form = new FormData()
    form.append('file', file)
    return request(path, { method: 'POST', body: form })
  },
}

export function connect(onMessage, onStatus) {
  let socket = null
  let retry = null
  let closed = false

  const open = () => {
    if (closed) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    socket = new WebSocket(`${proto}://${location.host}/ws`)
    socket.onopen = () => onStatus?.('connected')
    socket.onmessage = (event) => {
      try { onMessage(JSON.parse(event.data)) } catch (error) { console.error(error) }
    }
    socket.onclose = () => {
      onStatus?.('disconnected')
      if (!closed) retry = setTimeout(open, 1200)
    }
    socket.onerror = () => socket?.close()
  }
  open()
  return () => {
    closed = true
    clearTimeout(retry)
    socket?.close()
  }
}

export function timeAgo(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000)
  if (seconds < 45) return 'just now'
  if (seconds < 3600) {
    const minutes = Math.max(1, Math.round(seconds / 60))
    return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  }
  if (seconds < 86400) {
    const hours = Math.round(seconds / 3600)
    return `${hours} hour${hours === 1 ? '' : 's'} ago`
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function clock(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function day(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function relativeRun(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const now = new Date()
  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (date.toDateString() === now.toDateString()) return `Today ${time}`
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1)
  if (date.toDateString() === tomorrow.toDateString()) return `Tomorrow ${time}`
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`
  return `${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, ${time}`
}
