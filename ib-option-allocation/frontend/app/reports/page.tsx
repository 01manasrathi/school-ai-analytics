"use client";
import { useEffect, useState } from "react";
import { api, downloadCsv, errorText } from "@/lib/api";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { IconDownload } from "@/components/icons";

const REPORTS = [
  { key: "capacity", label: "Capacity", hint: "Seats, enrollment and status for every offering" },
  { key: "waitlist", label: "Waitlist", hint: "Who is waiting for which full class, in order" },
  { key: "unallocated", label: "Unallocated", hint: "New students with missing or partial placements" },
  { key: "allocation", label: "Allocation", hint: "One row per student, one column per block" },
  { key: "change-requests", label: "Change requests", hint: "Every request with feasibility and override info" },
];

export default function ReportsPage() {
  const [active, setActive] = useState("capacity");
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows([]); setError(null); setLoading(true);
    api(`/api/reports/${active}`).then(setRows).catch((e) => setError(errorText(e))).finally(() => setLoading(false));
  }, [active]);

  const display = active === "change-requests"
    ? rows.map((c) => ({ id: c.id, student: `${c.student_id} ${c.student_name}`,
        current: `${c.current_offering.subject} ${c.current_offering.level}`,
        requested: `${c.requested_offering.subject} ${c.requested_offering.level}`,
        feasibility: c.feasibility_status, status: c.status,
        reasons: (c.feasibility.reasons || []).join("; "), override: c.override_reason || "" }))
    : rows;
  const cols = display[0] ? Object.keys(display[0]) : [];
  const meta = REPORTS.find((r) => r.key === active)!;

  return (
    <div className="space-y-5">
      <PageHeader title="Reports" subtitle={meta.hint}>
        <button className="btn" onClick={() => downloadCsv(`/api/reports/${active}`, `${active}_report.csv`).catch((e) => setError(errorText(e)))}>
          <IconDownload /> Export CSV
        </button>
      </PageHeader>

      <div className="flex flex-wrap gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        {REPORTS.map((r) => (
          <button key={r.key} className={`tab ${active === r.key ? "tab-active" : ""}`} onClick={() => setActive(r.key)} title={r.hint}>{r.label}</button>
        ))}
      </div>

      <ErrorBox error={error} />
      {loading ? <Spinner /> : (
        <div className="card p-0">
          <div className="px-4 py-2 border-b border-slate-100 muted">{display.length} rows</div>
          {display.length === 0 ? <p className="muted p-4">No rows for this report.</p> : (
            <div className="overflow-auto scroll-thin max-h-[70vh]">
              <table className="tbl">
                <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
                <tbody>{display.map((r: any, i: number) => (
                  <tr key={i}>{cols.map((c) => (
                    <td key={c} className="whitespace-nowrap">
                      {["status", "feasibility", "feasibility_status"].includes(c) ? <Badge status={String(r[c])} />
                        : typeof r[c] === "boolean" ? (r[c] ? <span className="text-emerald-600 font-bold">✓</span> : <span className="text-rose-600 font-bold">✗</span>)
                        : typeof r[c] === "number" ? <span className="tabular-nums">{r[c]}</span>
                        : <span className={c === "reasons" || c === "issues" ? "text-xs text-slate-600" : ""}>{String(r[c] ?? "")}</span>}
                    </td>
                  ))}</tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
