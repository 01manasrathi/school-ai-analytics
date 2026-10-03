"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, errorText } from "@/lib/api";
import { AdminOnly, Badge, ErrorBox, FeasibilityResult, PageHeader, Spinner, SuccessBox } from "@/components/ui";
import { IconShield } from "@/components/icons";

const fmt = (o: any) => (o ? `${o.subject} ${o.level} · Block ${o.block} · ${o.current_enrollment}/${o.capacity}` : "");

function OverrideInner() {
  const params = useSearchParams();
  const [crs, setCrs] = useState<any[]>([]);
  const [selected, setSelected] = useState<number | null>(params.get("cr") ? Number(params.get("cr")) : null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [log, setLog] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api("/api/change-requests").then((all) =>
      setCrs(all.filter((c: any) => ["PENDING", "WAITLISTED", "OVERRIDDEN"].includes(c.status))));
    api("/api/audit-log?limit=50").then(setLog);
  };
  useEffect(load, []);

  const cr = crs.find((c) => c.id === selected);
  const open = crs.filter((c) => c.status !== "OVERRIDDEN");

  const submit = async () => {
    setBusy(true); setError(null); setDone(null);
    try {
      const r = await api(`/api/change-request/${selected}/override`, { body: { reason } });
      setDone(`Change request #${r.id} overridden. Enrollment updated and an audit entry was written.`);
      setReason("");
      load();
    } catch (e) { setError(errorText(e)); }
    setBusy(false);
  };

  return (
    <div className="space-y-5">
      <PageHeader title="Admin Override" subtitle="Force a change that the rules would block — reason required, fully audited" />

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="card">
          <h2 className="h2">Open requests</h2>
          {open.length === 0 ? <p className="muted">No open requests.</p> : (
            <ul className="space-y-1">{open.map((c) => (
              <li key={c.id}>
                <button onClick={() => { setSelected(c.id); setDone(null); setError(null); }}
                  className={`w-full text-left rounded-lg px-3 py-2 ring-1 transition ${selected === c.id ? "bg-indigo-50 ring-indigo-300" : "ring-transparent hover:bg-slate-50"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-slate-500">#{c.id} {c.student_id}</span>
                    <Badge status={c.feasibility_status} />
                  </div>
                  <div className="text-sm font-medium text-slate-800 mt-0.5">{c.requested_offering.subject} {c.requested_offering.level}</div>
                </button>
              </li>
            ))}</ul>
          )}
        </div>

        <div className="lg:col-span-2 space-y-3">
          {cr ? (
            <>
              <div className="card space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs bg-slate-100 rounded px-1.5 py-0.5 text-slate-600">{cr.student_id}</span>
                  <span className="font-semibold text-slate-900">{cr.student_name}</span>
                  <Badge status={cr.status} />
                </div>
                <div className="text-sm"><span className="label inline mr-1">From</span> {fmt(cr.current_offering)}</div>
                <div className="text-sm"><span className="label inline mr-1">To</span> <b>{fmt(cr.requested_offering)}</b></div>
                {cr.compensating_current_offering && (
                  <div className="text-sm"><span className="label inline mr-1">Also</span> {fmt(cr.compensating_current_offering)} → {fmt(cr.compensating_requested_offering)}</div>
                )}
                <div className="muted">Reason given: {cr.reason || "—"}</div>
              </div>

              <FeasibilityResult result={cr.feasibility} />

              {cr.status !== "OVERRIDDEN" ? (
                <div className="card space-y-2">
                  <label className="label">Override reason (required, minimum 5 characters)</label>
                  <textarea className="input h-24" placeholder="e.g. DP coordinator approved a reduced HL load on medical grounds"
                    value={reason} onChange={(e) => setReason(e.target.value)} />
                  <AdminOnly>
                    <button className="btn-danger" disabled={reason.trim().length < 5 || busy} onClick={submit}>
                      <IconShield /> {busy ? "Applying…" : "Apply override"}
                    </button>
                  </AdminOnly>
                  <p className="text-xs text-slate-500">
                    The move runs in a single transaction (source −1, target +1, choice history kept) and is written to the audit log.
                    Hard conflicts — block clash, duplicate subject, timetable clash — can never be overridden.
                  </p>
                </div>
              ) : (
                <div className="card text-sm">
                  Overridden by <b>{cr.override_by}</b>: {cr.override_reason}
                </div>
              )}
            </>
          ) : <div className="card muted">Select a change request on the left.</div>}
          <ErrorBox error={error} />
          <SuccessBox message={done} />
        </div>
      </div>

      <div className="card p-0">
        <div className="p-4 pb-2"><h2 className="h2 mb-0">Audit log · latest 50 entries</h2></div>
        <div className="overflow-auto scroll-thin max-h-96">
          <table className="tbl">
            <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>Old value</th><th>New value</th></tr></thead>
            <tbody>{log.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap text-xs text-slate-500">{new Date(a.timestamp).toLocaleString()}</td>
                <td className="text-sm">{a.user}</td>
                <td><span className="chip bg-slate-100 text-slate-700 ring-slate-200">{a.action}</span></td>
                <td className="text-xs text-slate-600">{a.entity} {a.entity_id}</td>
                <td className="text-xs max-w-xs truncate" title={a.old_value}>{a.old_value}</td>
                <td className="text-xs max-w-md truncate" title={a.new_value}>{a.new_value}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function OverridePage() {
  return <Suspense fallback={<Spinner />}><OverrideInner /></Suspense>;
}
