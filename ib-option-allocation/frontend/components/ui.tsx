"use client";
import { useAuth } from "./AuthProvider";
import { IconCheck, IconWarning, IconX } from "./icons";

const STATUS: Record<string, string> = {
  FEASIBLE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  FEASIBLE_WAITLIST: "bg-amber-50 text-amber-700 ring-amber-200",
  NEEDS_OVERRIDE: "bg-orange-50 text-orange-700 ring-orange-200",
  NOT_FEASIBLE: "bg-rose-50 text-rose-700 ring-rose-200",
  PENDING: "bg-sky-50 text-sky-700 ring-sky-200",
  APPROVED: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  WAITLISTED: "bg-amber-50 text-amber-700 ring-amber-200",
  REJECTED: "bg-slate-100 text-slate-600 ring-slate-300",
  OVERRIDDEN: "bg-violet-50 text-violet-700 ring-violet-200",
  ALLOCATED: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  PARTIAL: "bg-amber-50 text-amber-700 ring-amber-200",
  UNALLOCATED: "bg-rose-50 text-rose-700 ring-rose-200",
  EMPTY: "bg-slate-100 text-slate-600 ring-slate-300",
  OK: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  FULL: "bg-amber-50 text-amber-700 ring-amber-200",
  OVER_CAPACITY: "bg-rose-50 text-rose-700 ring-rose-200",
  BELOW_MIN: "bg-sky-50 text-sky-700 ring-sky-200",
  EXISTING: "bg-slate-100 text-slate-700 ring-slate-300",
  NEW: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  WITHDRAWN: "bg-slate-100 text-slate-500 ring-slate-300",
};

export function Badge({ status, className = "" }: { status?: string | null; className?: string }) {
  if (!status) return null;
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-bold tracking-wide ring-1 ${STATUS[status] || "bg-slate-100 text-slate-600 ring-slate-300"} ${className}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

const TONES: Record<string, string> = {
  slate: "from-slate-500 to-slate-600", rose: "from-rose-500 to-rose-600", amber: "from-amber-500 to-amber-600",
  emerald: "from-emerald-500 to-emerald-600", indigo: "from-indigo-500 to-indigo-600", sky: "from-sky-500 to-sky-600",
};

export function Stat({ label, value, sub, tone = "slate", icon }: { label: string; value: any; sub?: string; tone?: string; icon?: React.ReactNode }) {
  return (
    <div className="card relative overflow-hidden">
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${TONES[tone] || TONES.slate}`} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
          <div className="text-3xl font-bold text-slate-900 mt-1 tabular-nums">{value}</div>
          {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
        </div>
        {icon && <div className="text-slate-300">{icon}</div>}
      </div>
    </div>
  );
}

export function ErrorBox({ error }: { error?: string | null }) {
  if (!error) return null;
  return (
    <div className="flex gap-2 rounded-xl bg-rose-50 ring-1 ring-rose-200 p-3 text-sm text-rose-800">
      <IconWarning className="w-5 h-5 shrink-0 mt-0.5" />
      <pre className="whitespace-pre-wrap font-sans">{error}</pre>
    </div>
  );
}

export function SuccessBox({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div className="flex gap-2 rounded-xl bg-emerald-50 ring-1 ring-emerald-200 p-3 text-sm text-emerald-800">
      <IconCheck className="w-5 h-5 shrink-0" /> <span>{message}</span>
    </div>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="h1">{title}</h1>
        {subtitle && <p className="muted mt-1">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500 py-6">
      <span className="w-4 h-4 rounded-full border-2 border-slate-300 border-t-indigo-500 animate-spin" />
      {label}
    </div>
  );
}

export function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <span className="text-xs italic text-slate-400">Read-only role — action disabled</span>;
  return <>{children}</>;
}

export function GroupCoverage({ coverage, required = ["1", "2", "3", "4", "5"] }: { coverage: Record<string, any>; required?: string[] }) {
  return (
    <span className="inline-flex gap-1">
      {Object.entries(coverage).map(([g, n]) => {
        const missing = required.includes(g) && !n;
        return (
          <span key={g} className={`chip ${missing ? "bg-rose-50 text-rose-700 ring-rose-200" : n ? "bg-slate-100 text-slate-600 ring-slate-200" : "bg-slate-50 text-slate-400 ring-slate-200"}`}>
            G{g}<span className="tabular-nums">{String(n)}</span>
          </span>
        );
      })}
    </span>
  );
}

export function HlSl({ hl, sl, okHl = 4, okSl = 3 }: { hl: number; sl: number; okHl?: number; okSl?: number }) {
  const ok = hl === okHl && sl === okSl;
  return (
    <span className={`chip ${ok ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-rose-50 text-rose-700 ring-rose-200"}`}>
      {ok ? <IconCheck className="w-3 h-3" /> : <IconX className="w-3 h-3" />}
      {hl} HL / {sl} SL
    </span>
  );
}

export function FeasibilityResult({ result }: { result: any }) {
  if (!result) return null;
  const imp = result.impact || {};
  const bc = Array.isArray(imp.blockChange) ? imp.blockChange : imp.blockChange ? [imp.blockChange] : [];
  const tone = result.status === "FEASIBLE" ? "border-emerald-300 bg-emerald-50/40"
    : result.status === "NOT_FEASIBLE" ? "border-rose-300 bg-rose-50/40" : "border-amber-300 bg-amber-50/40";
  const Cell = ({ label, children }: any) => (
    <div className="rounded-lg bg-white ring-1 ring-slate-200 px-3 py-2">
      <div className="label mb-0.5">{label}</div>
      <div className="text-sm font-medium text-slate-800">{children}</div>
    </div>
  );
  return (
    <div className={`rounded-xl border-l-4 ${tone} ring-1 ring-slate-200 p-4 space-y-3`}>
      <div className="flex flex-wrap items-center gap-3">
        <Badge status={result.status} className="text-xs px-2.5 py-1" />
        {result.status !== "FEASIBLE" && (
          <span className="text-xs text-slate-500">
            {result.override_allowed ? "Admin override allowed with a reason" : "Hard conflict — cannot be overridden"}
          </span>
        )}
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <div className="label">Reasons</div>
          <ul className="space-y-1 text-sm">{result.reasons.map((r: string, i: number) => (
            <li key={i} className="flex gap-1.5">
              <span className={result.status === "FEASIBLE" ? "text-emerald-600" : "text-rose-500"}>•</span><span>{r}</span>
            </li>
          ))}</ul>
        </div>
        {result.warnings?.length > 0 && (
          <div>
            <div className="label">Warnings</div>
            <ul className="space-y-1 text-sm text-amber-800">{result.warnings.map((r: string, i: number) => (
              <li key={i} className="flex gap-1.5"><span>⚠</span><span>{r}</span></li>
            ))}</ul>
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Cell label="Target seats after"><span className="tabular-nums">{imp.targetSeatsAfter}</span></Cell>
        <Cell label="Source seats after"><span className="tabular-nums">{imp.sourceSeatsAfter}</span></Cell>
        <Cell label="Block change">
          {bc.map((b: any, i: number) => (
            <div key={i} className="text-xs">{b.from} → {b.to} <span className="text-slate-400">{b.changed ? "cross-block" : "same block"}</span></div>
          ))}
        </Cell>
        <Cell label="HL / SL after"><HlSl hl={imp.hlSlAfter?.hl ?? 0} sl={imp.hlSlAfter?.sl ?? 0} /></Cell>
        <Cell label="Group coverage after">{imp.groupCoverageAfter && <GroupCoverage coverage={imp.groupCoverageAfter} />}</Cell>
      </div>
    </div>
  );
}

export function BlockGrid({ student }: { student: any }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
      {student.blocks.map((b: any) => {
        const c = b.choice;
        const tone = !c ? "bg-rose-50 ring-rose-200"
          : c.level === "HL" ? "bg-indigo-50 ring-indigo-200" : "bg-teal-50 ring-teal-200";
        return (
          <div key={b.block_id} className={`rounded-lg ring-1 p-2 ${tone}`} title={b.label}>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Block {b.block}</span>
              {c && <span className={`text-[10px] font-bold px-1 rounded ${c.level === "HL" ? "bg-indigo-600 text-white" : "bg-teal-600 text-white"}`}>{c.level}</span>}
            </div>
            {c ? (
              <>
                <div className="text-[13px] font-semibold text-slate-800 leading-snug mt-1">{c.subject}</div>
                <div className="text-[10px] text-slate-500">Group {c.group}</div>
              </>
            ) : <div className="text-xs text-rose-600 mt-1">— empty —</div>}
            {b.waitlisted.map((w: any) => (
              <div key={w.choice_id} className="mt-1 text-[10px] font-semibold text-amber-700 bg-amber-100 rounded px-1 py-0.5">
                Waitlist: {w.subject} {w.level}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
