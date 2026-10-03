// Small inline SVG icon set (no icon library needed).
type P = { className?: string };
const base = "w-4 h-4";
const wrap = (d: React.ReactNode) => (p: P) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"
    className={p.className || base} aria-hidden>
    {d}
  </svg>
);

export const IconDashboard = wrap(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="11" width="7" height="10" rx="1.5" /><rect x="3" y="15" width="7" height="6" rx="1.5" /></>);
export const IconUpload = wrap(<><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></>);
export const IconGrid = wrap(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 4v16M3 12h18" /></>);
export const IconUserPlus = wrap(<><circle cx="9" cy="8" r="3.5" /><path d="M3 20c0-3.3 2.7-6 6-6h1" /><path d="M17 11v6M14 14h6" /></>);
export const IconSwap = wrap(<><path d="M4 8h13l-3-3M20 16H7l3 3" /></>);
export const IconShield = wrap(<><path d="M12 3l7 3v6c0 4.2-2.9 7.9-7 9-4.1-1.1-7-4.8-7-9V6l7-3Z" /><path d="m9 12 2 2 4-4" /></>);
export const IconReport = wrap(<><path d="M5 3h9l5 5v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M14 3v5h5" /><path d="M8 13h8M8 17h5" /></>);
export const IconSettings = wrap(<><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" /></>);
export const IconDownload = wrap(<><path d="M12 4v12" /><path d="m7 11 5 5 5-5" /><path d="M4 20h16" /></>);
export const IconPlay = wrap(<><path d="M7 4l12 8-12 8V4Z" /></>);
export const IconCheck = wrap(<><path d="m5 13 4 4L19 7" /></>);
export const IconX = wrap(<><path d="M6 6l12 12M18 6 6 18" /></>);
export const IconRefresh = wrap(<><path d="M20 12a8 8 0 1 1-2.3-5.7" /><path d="M20 4v5h-5" /></>);
export const IconLogout = wrap(<><path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4" /><path d="M16 8l4 4-4 4M20 12H9" /></>);
export const IconSearch = wrap(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>);
export const IconWarning = wrap(<><path d="M12 4l9 16H3l9-16Z" /><path d="M12 10v4M12 17h.01" /></>);
export const IconPlus = wrap(<><path d="M12 5v14M5 12h14" /></>);
export const IconSave = wrap(<><path d="M5 3h11l3 3v15H5V3Z" /><path d="M8 3v6h8V3M8 21v-6h8v6" /></>);
