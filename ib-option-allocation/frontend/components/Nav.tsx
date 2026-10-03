"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthProvider";
import {
  IconDashboard, IconGrid, IconLogout, IconReport, IconSettings, IconShield, IconSwap, IconUpload, IconUserPlus,
} from "./icons";

const LINKS: [string, string, (p: { className?: string }) => JSX.Element][] = [
  ["/", "Dashboard", IconDashboard],
  ["/import", "Import CSV", IconUpload],
  ["/allocations", "Existing Allocations", IconGrid],
  ["/new-allocation", "New Student Allocation", IconUserPlus],
  ["/change-requests", "Change Requests", IconSwap],
  ["/override", "Admin Override", IconShield],
  ["/reports", "Reports", IconReport],
  ["/settings", "Settings", IconSettings],
];

export default function Nav() {
  const path = usePathname();
  const { user, logout } = useAuth();
  if (path === "/login" || !user) return null;
  return (
    <aside className="w-64 shrink-0 sticky top-0 h-screen bg-slate-900 text-slate-300 flex flex-col">
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-400 to-violet-500 grid place-items-center text-white font-bold shadow-lg shadow-indigo-900/40">IB</div>
          <div className="leading-tight">
            <div className="font-semibold text-white text-[15px]">Option Allocation</div>
            <div className="text-[11px] text-slate-400">& Change Feasibility</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto scroll-thin">
        {LINKS.map(([href, label, Icon]) => {
          const active = path === href;
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition
                ${active ? "bg-indigo-600 text-white font-semibold shadow-sm" : "hover:bg-slate-800 hover:text-white"}`}>
              <Icon className="w-[18px] h-[18px] shrink-0" />
              <span className="truncate">{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="m-3 rounded-lg bg-slate-800/70 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-slate-700 grid place-items-center text-xs font-bold text-white uppercase">
            {user.username.slice(0, 2)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm text-white truncate">{user.username}</div>
            <div className="text-[11px] text-slate-400">{user.role === "ADMIN" ? "Admin / Timetabler" : "Read-only"}</div>
          </div>
          <button onClick={logout} title="Log out" className="p-1.5 rounded-md hover:bg-slate-700 hover:text-white">
            <IconLogout />
          </button>
        </div>
      </div>
    </aside>
  );
}
