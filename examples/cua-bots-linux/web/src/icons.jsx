import React from 'react'

const PATHS = {
  plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
  plusBubble: <><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.9 8.9 0 0 1-3.8-.85L3 21l1.95-5.2A8.4 8.4 0 1 1 21 11.5Z" /><path d="M12 8v7" /><path d="M8.5 11.5h7" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  shield: <><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3Z" /><path d="m9 12 2 2 4-4" /></>,
  tray: <><path d="M4 4h16v16H4z" /><path d="M4 14h4l2 3h4l2-3h4" /></>,
  desktop: <><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8" /><path d="M12 16v4" /></>,
  laptop: <><rect x="4" y="5" width="16" height="11" rx="2" /><path d="M2 20h20" /></>,
  pause: <><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></>,
  play: <path d="M8 5v14l11-7-11-7Z" />,
  sidebar: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></>,
  x: <><path d="M6 6l12 12" /><path d="M18 6 6 18" /></>,
  chevronRight: <path d="m9 5 7 7-7 7" />,
  chevronDown: <path d="m5 9 7 7 7-7" />,
  chevronUp: <path d="m5 15 7-7 7 7" />,
  file: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z" /><path d="M14 3v6h6" /></>,
  bell: <><path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
  brain: <><path d="M9.5 4A3.5 3.5 0 0 0 6 7.5 3 3 0 0 0 4 13a3 3 0 0 0 2 5.2A3.5 3.5 0 0 0 9.5 21 3.5 3.5 0 0 0 13 17.5v-10A3.5 3.5 0 0 0 9.5 4Z" /><path d="M14.5 4A3.5 3.5 0 0 1 18 7.5 3 3 0 0 1 20 13a3 3 0 0 1-2 5.2A3.5 3.5 0 0 1 14.5 21 3.5 3.5 0 0 1 11 17.5" /></>,
  checklist: <><path d="M9 6h11" /><path d="M9 12h11" /><path d="M9 18h11" /><path d="m3 6 1.5 1.5L7 5" /><path d="m3 12 1.5 1.5L7 11" /><path d="m3 18 1.5 1.5L7 17" /></>,
  key: <><circle cx="8" cy="8" r="4" /><path d="m11 11 9 9" /><path d="m16 16 2-2" /><path d="m19 19 2-2" /></>,
  cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" /></>,
  ellipsis: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" /></>,
  pencil: <><path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z" /><path d="m14 6 4 4" /></>,
  lock: <><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  arrowUp: <><path d="M12 20V4" /><path d="m5 11 7-7 7 7" /></>,
  message: <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.9 8.9 0 0 1-3.8-.85L3 21l1.95-5.2A8.4 8.4 0 1 1 21 11.5Z" />,
  pip: <><rect x="3" y="4" width="18" height="16" rx="2" /><rect x="12" y="12" width="7" height="6" rx="1" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  alert: <><path d="M12 3 2 21h20L12 3Z" /><path d="M12 9v5" /><path d="M12 18h.01" /></>,
  refresh: <><path d="M20 11a8 8 0 0 0-14.9-4M4 5v6h6" /><path d="M4 13a8 8 0 0 0 14.9 4M20 19v-6h-6" /></>,
  doc: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z" /><path d="M14 3v6h6" /><path d="M8 13h8M8 17h8" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.5" /><path d="m21 15-5-5L5 20" /></>,
  table: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 4v16M15 4v16" /></>,
  clockSmall: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 1.5" /></>,
  circleDashed: <><circle cx="12" cy="12" r="8" strokeDasharray="3 3" /><path d="M12 8v4l2 1" /></>,
  pauseCircle: <><circle cx="12" cy="12" r="9" /><path d="M10 9v6M14 9v6" /></>,
  checkCircle: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
  alertCircle: <><circle cx="12" cy="12" r="9" /><path d="M12 8v5" /><path d="M12 16h.01" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0" /><path d="M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 5" /></>,
  link: <><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" /></>,
  upload: <><path d="M12 16V4" /><path d="m6 10 6-6 6 6" /><path d="M4 20h16" /></>,
}

export function Icon({ name, size = 18, className = '', strokeWidth = 1.8 }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      {PATHS[name] || PATHS.circleDashed}
    </svg>
  )
}
