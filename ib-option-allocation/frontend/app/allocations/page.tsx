"use client";
import { useEffect, useMemo, useState } from "react";
import { api, downloadCsv, errorText } from "@/lib/api";
import { Badge, BlockGrid, ErrorBox, GroupCoverage, HlSl, PageHeader, Spinner } from "@/components/ui";
import { IconDownload, IconGrid, IconReport, IconSearch } from "@/components/icons";

export default function AllocationsPage() {
  const [students, setStudents] = useState<any[]>([]);
  const [status, setStatus] = useState("EXISTING");
  const [q, setQ] = useState("");
  const [subject, setSubject] = useState("");
  const [view, setView] = useState<"grid" | "table">("grid");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api(`/api/students${status ? `?status=${status}` : ""}`)
      .then(setStudents).catch((e) => setError(errorText(e))).finally(() => setLoading(false));
  }, [status]);

  const subjects = useMemo(() => {
    const s = new Set<string>();
    students.forEach((st) => st.blocks.forEach((b: any) => b.choice && s.add(b.choice.subject)));
    return Array.from(s).sort();
  }, [students]);

  const filtered = students.filter((s) =>
    (!q || s.name.toLowerCase().includes(q.toLowerCase()) || s.student_id.toLowerCase().includes(q.toLowerCase())) &&
    (!subject || s.blocks.some((b: any) => b.choice?.subject === subject)) &&
    (!onlyIssues || !s.valid));

  const blockNames: string[] = students[0]?.blocks.map((b: any) => b.block) || [];
  const invalid = students.filter((s) => !s.valid).length;

  return (
    <div className="space-y-5">
      <PageHeader title="Existing Allocations" subtitle="Block grid per student with HL/SL counters and group coverage">
        <button className="btn-secondary" onClick={() => downloadCsv(`/api/reports/allocation${status ? `?status=${status}` : ""}`, "allocation_report.csv").catch((e) => setError(errorText(e)))}>
          <IconDownload /> Export CSV
        </button>
      </PageHeader>

      <div className="card-tight flex flex-wrap items-end gap-3">
        <div className="w-36">
          <label className="label">Status</label>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option><option>EXISTING</option><option>NEW</option><option>WITHDRAWN</option>
          </select>
        </div>
        <div className="w-56">
          <label className="label">Search</label>
          <div className="relative">
            <IconSearch className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" />
            <input className="input pl-8" placeholder="Name or student ID" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="w-60">
          <label className="label">Takes subject</label>
          <select className="input" value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">Any subject</option>{subjects.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-700 pb-1.5">
          <input type="checkbox" className="rounded border-slate-300" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} />
          Only rule issues {invalid > 0 && <span className="chip bg-rose-50 text-rose-700 ring-rose-200">{invalid}</span>}
        </label>
        <div className="ml-auto flex gap-1 bg-slate-100 p-1 rounded-lg">
          <button className={`tab ${view === "grid" ? "tab-active" : ""}`} onClick={() => setView("grid")}><IconGrid className="w-4 h-4 inline mr-1" />Block grid</button>
          <button className={`tab ${view === "table" ? "tab-active" : ""}`} onClick={() => setView("table")}><IconReport className="w-4 h-4 inline mr-1" />Table</button>
        </div>
      </div>

      <ErrorBox error={error} />
      {loading ? <Spinner /> : <div className="muted">{filtered.length} of {students.length} students</div>}

      {!loading && view === "grid" && (
        <div className="space-y-3">
          {filtered.map((s) => (
            <div key={s.id} className="card">
              <div className="flex flex-wrap items-center gap-2.5 mb-3">
                <span className="font-mono text-xs bg-slate-100 rounded px-1.5 py-0.5 text-slate-600">{s.student_id}</span>
                <span className="font-semibold text-slate-900">{s.name}</span>
                <span className="muted text-xs">Grade {s.grade} · {s.programme} · {s.nationality}</span>
                <Badge status={s.status} />
                <div className="ml-auto flex items-center gap-2">
                  <HlSl hl={s.hl} sl={s.sl} />
                  <GroupCoverage coverage={s.group_coverage} />
                  {s.allocated
                    ? s.valid ? <span className="chip bg-emerald-50 text-emerald-700 ring-emerald-200">Rules OK</span>
                              : <span className="chip bg-rose-50 text-rose-700 ring-rose-200">Rule issues</span>
                    : <span className="chip bg-slate-100 text-slate-500 ring-slate-200">Not allocated</span>}
                </div>
              </div>
              <BlockGrid student={s} />
              {s.issues.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs text-rose-700">
                  {s.issues.map((i: any, k: number) => <li key={k}>• [{i.severity}] {i.message}</li>)}
                </ul>
              )}
            </div>
          ))}
          {filtered.length === 0 && <div className="card muted">No students match these filters.</div>}
        </div>
      )}

      {!loading && view === "table" && (
        <div className="card p-0 overflow-auto scroll-thin max-h-[70vh]">
          <table className="tbl">
            <thead><tr><th>ID</th><th>Name</th>{blockNames.map((b) => <th key={b}>Block {b}</th>)}<th>HL/SL</th><th>Groups</th><th>Valid</th></tr></thead>
            <tbody>{filtered.map((s) => (
              <tr key={s.id}>
                <td className="font-mono text-xs">{s.student_id}</td>
                <td className="font-medium whitespace-nowrap">{s.name}</td>
                {s.blocks.map((b: any) => (
                  <td key={b.block_id} className="whitespace-nowrap text-xs">
                    {b.choice ? <>{b.choice.subject_code} <span className={`font-bold ${b.choice.level === "HL" ? "text-indigo-600" : "text-teal-600"}`}>{b.choice.level}</span></> : <span className="text-slate-300">—</span>}
                  </td>
                ))}
                <td><HlSl hl={s.hl} sl={s.sl} /></td>
                <td><GroupCoverage coverage={s.group_coverage} /></td>
                <td>{s.valid ? <span className="text-emerald-600 font-bold">✓</span> : <span className="text-rose-600 font-bold">✗</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
