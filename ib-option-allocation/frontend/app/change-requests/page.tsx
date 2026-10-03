"use client";
import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { api, downloadCsv, errorText } from "@/lib/api";
import { AdminOnly, Badge, BlockGrid, ErrorBox, FeasibilityResult, PageHeader, Spinner } from "@/components/ui";
import { IconCheck, IconDownload, IconRefresh, IconShield, IconSwap, IconX } from "@/components/icons";

const fmt = (o: any) => (o ? `${o.subject} ${o.level} (${o.block})` : "");

export default function ChangeRequestsPage() {
  const [students, setStudents] = useState<any[]>([]);
  const [offerings, setOfferings] = useState<any[]>([]);
  const [crs, setCrs] = useState<any[]>([]);
  const [studentId, setStudentId] = useState("");
  const [student, setStudent] = useState<any>(null);
  const [current, setCurrent] = useState("");
  const [requested, setRequested] = useState("");
  const [compCurrent, setCompCurrent] = useState("");
  const [compRequested, setCompRequested] = useState("");
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState(3);
  const [result, setResult] = useState<any>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState("");

  const loadCrs = () => api("/api/change-requests").then(setCrs);
  useEffect(() => {
    api("/api/students").then((s) => setStudents(s.filter((x: any) => x.allocated)));
    api("/api/offerings").then(setOfferings);
    loadCrs();
  }, []);

  useEffect(() => {
    setStudent(null); setCurrent(""); setRequested(""); setCompCurrent(""); setCompRequested(""); setResult(null);
    if (studentId) api(`/api/students/${studentId}`).then(setStudent);
  }, [studentId]);

  useEffect(() => {
    setResult(null);
    if (!student || !current || !requested) return;
    const body: any = { student_id: student.student_id, current_offering_id: Number(current), requested_offering_id: Number(requested) };
    if (compCurrent && compRequested) {
      body.compensating_current_offering_id = Number(compCurrent);
      body.compensating_requested_offering_id = Number(compRequested);
    }
    setChecking(true);
    api("/api/feasibility/check", { body }).then(setResult).catch((e) => setError(errorText(e))).finally(() => setChecking(false));
  }, [student, current, requested, compCurrent, compRequested]);

  const myChoices = student ? student.blocks.filter((b: any) => b.choice).map((b: any) => b.choice) : [];
  const byBlock = offerings.reduce((acc: Record<string, any[]>, o) => { (acc[o.block] ||= []).push(o); return acc; }, {});

  const submit = async () => {
    setError(null);
    try {
      await api("/api/change-request", { body: {
        student_id: student.student_id, current_offering_id: Number(current), requested_offering_id: Number(requested),
        compensating_current_offering_id: compCurrent ? Number(compCurrent) : null,
        compensating_requested_offering_id: compRequested ? Number(compRequested) : null, reason, priority } });
      setReason(""); setStudentId(""); loadCrs();
    } catch (e) { setError(errorText(e)); }
  };

  const act = async (id: number, action: "approve" | "reject" | "recheck") => {
    setError(null);
    try { await api(`/api/change-request/${id}/${action}`, { body: action === "reject" ? { reason: "Rejected by timetabler" } : {} }); }
    catch (e) { setError(errorText(e)); }
    loadCrs();
    api("/api/offerings").then(setOfferings);
  };

  const OfferingSelect = ({ value, onChange, exclude }: any) => (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">— choose —</option>
      {Object.entries(byBlock).map(([blk, list]) => (
        <optgroup key={blk} label={`Block ${blk}`}>
          {(list as any[]).filter((o) => o.is_active && o.id !== Number(exclude)).map((o) => (
            <option key={o.id} value={o.id}>{o.subject} {o.level} — {o.current_enrollment}/{o.capacity}{o.full ? " FULL" : ""}</option>
          ))}
        </optgroup>
      ))}
    </select>
  );

  const shown = filter ? crs.filter((c) => c.status === filter) : crs;
  const counts = crs.reduce((a: Record<string, number>, c) => { a[c.status] = (a[c.status] || 0) + 1; return a; }, {});

  return (
    <div className="space-y-5">
      <PageHeader title="Change Requests" subtitle="Live feasibility check before anything is saved">
        <button className="btn-secondary" onClick={() => downloadCsv("/api/reports/change-requests", "change_requests.csv").catch((e) => setError(errorText(e)))}>
          <IconDownload /> Export CSV
        </button>
      </PageHeader>

      <div className="card space-y-4">
        <h2 className="h2 flex items-center gap-2 mb-0"><IconSwap className="text-indigo-500" /> Test a change</h2>
        <div className="grid md:grid-cols-4 gap-3">
          <div>
            <label className="label">Student</label>
            <select className="input" value={studentId} onChange={(e) => setStudentId(e.target.value)}>
              <option value="">— choose —</option>
              {students.map((s) => <option key={s.id} value={s.student_id}>{s.student_id} · {s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Current subject</label>
            <select className="input" value={current} onChange={(e) => setCurrent(e.target.value)} disabled={!student}>
              <option value="">— choose —</option>
              {myChoices.map((c: any) => <option key={c.offering_id} value={c.offering_id}>{c.subject} {c.level} (Block {c.block})</option>)}
            </select>
          </div>
          <div><label className="label">Requested subject / level</label><OfferingSelect value={requested} onChange={setRequested} exclude={current} /></div>
          <div>
            <label className="label">Priority (1 = highest)</label>
            <input className="input" type="number" min={1} max={5} value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
          </div>
        </div>

        <details className="rounded-lg bg-slate-50 ring-1 ring-slate-200 p-3">
          <summary className="cursor-pointer text-sm font-medium text-indigo-700">Optional compensating change (fix the HL/SL ratio or free the target block)</summary>
          <div className="grid md:grid-cols-2 gap-3 mt-3">
            <div>
              <label className="label">Also move from</label>
              <select className="input" value={compCurrent} onChange={(e) => setCompCurrent(e.target.value)}>
                <option value="">— none —</option>
                {myChoices.filter((c: any) => String(c.offering_id) !== current).map((c: any) => (
                  <option key={c.offering_id} value={c.offering_id}>{c.subject} {c.level} (Block {c.block})</option>))}
              </select>
            </div>
            <div><label className="label">…to</label><OfferingSelect value={compRequested} onChange={setCompRequested} exclude={compCurrent} /></div>
          </div>
        </details>

        <div><label className="label">Reason</label><input className="input" placeholder="Why is this change requested?" value={reason} onChange={(e) => setReason(e.target.value)} /></div>

        {student && (
          <div>
            <div className="label">Current programme</div>
            <BlockGrid student={student} />
          </div>
        )}
        {checking && <Spinner label="Checking feasibility…" />}
        <FeasibilityResult result={result} />
        <ErrorBox error={error} />
        <AdminOnly><button className="btn" disabled={!result} onClick={submit}>Submit change request</button></AdminOnly>
      </div>

      <div className="card p-0">
        <div className="p-4 pb-2 flex flex-wrap items-center gap-2">
          <h2 className="h2 mb-0">All change requests</h2>
          <div className="ml-auto flex gap-1 bg-slate-100 p-1 rounded-lg">
            <button className={`tab ${filter === "" ? "tab-active" : ""}`} onClick={() => setFilter("")}>All {crs.length}</button>
            {["PENDING", "APPROVED", "WAITLISTED", "OVERRIDDEN", "REJECTED"].filter((s) => counts[s]).map((s) => (
              <button key={s} className={`tab ${filter === s ? "tab-active" : ""}`} onClick={() => setFilter(s)}>{s} {counts[s]}</button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto scroll-thin">
          <table className="tbl">
            <thead><tr><th>#</th><th>Student</th><th>Current → Requested</th><th>Reason</th><th>P</th><th>Feasibility</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{shown.map((cr) => (
              <Fragment key={cr.id}>
                <tr className="cursor-pointer" onClick={() => setExpanded(expanded === cr.id ? null : cr.id)}>
                  <td className="tabular-nums text-slate-400">{cr.id}</td>
                  <td className="whitespace-nowrap">
                    <div className="font-mono text-xs text-slate-600">{cr.student_id}</div>
                    <div className="font-medium">{cr.student_name}</div>
                  </td>
                  <td className="text-sm">
                    <span className="text-slate-500">{fmt(cr.current_offering)}</span> → <b>{fmt(cr.requested_offering)}</b>
                    {cr.compensating_current_offering && (
                      <div className="text-xs text-slate-500">+ {fmt(cr.compensating_current_offering)} → {fmt(cr.compensating_requested_offering)}</div>
                    )}
                  </td>
                  <td className="text-xs text-slate-600 max-w-xs">{cr.reason}</td>
                  <td className="tabular-nums">{cr.priority}</td>
                  <td><Badge status={cr.feasibility_status} /></td>
                  <td><Badge status={cr.status} /></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {["PENDING", "WAITLISTED"].includes(cr.status) && (
                      <AdminOnly>
                        <div className="flex gap-1">
                          <button className="btn btn-xs" onClick={() => act(cr.id, "approve")}><IconCheck className="w-3 h-3" /> Approve</button>
                          <button className="btn-secondary btn-xs" title="Re-check feasibility" onClick={() => act(cr.id, "recheck")}><IconRefresh className="w-3 h-3" /></button>
                          <button className="btn-secondary btn-xs" title="Reject" onClick={() => act(cr.id, "reject")}><IconX className="w-3 h-3" /></button>
                          {cr.feasibility_status !== "FEASIBLE" && (
                            <Link className="btn-danger btn-xs" href={`/override?cr=${cr.id}`}><IconShield className="w-3 h-3" /> Override</Link>
                          )}
                        </div>
                      </AdminOnly>
                    )}
                  </td>
                </tr>
                {expanded === cr.id && (
                  <tr><td colSpan={8} className="bg-slate-50 p-4">
                    <FeasibilityResult result={cr.feasibility} />
                    {cr.override_reason && (
                      <div className="mt-2 text-sm rounded-lg bg-violet-50 ring-1 ring-violet-200 p-2">
                        Overridden by <b>{cr.override_by}</b>: {cr.override_reason}
                      </div>
                    )}
                  </td></tr>
                )}
              </Fragment>
            ))}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
