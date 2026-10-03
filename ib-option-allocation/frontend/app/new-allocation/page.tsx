"use client";
import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { AdminOnly, Badge, ErrorBox, HlSl, PageHeader, Spinner, SuccessBox } from "@/components/ui";
import { IconCheck, IconPlay, IconSave } from "@/components/icons";

type Slot = { block_id: number; block: string; offering_id: number | null; status: string; flag: string | null; reasons: string[]; subject?: string; level?: string };

export default function NewAllocationPage() {
  const [result, setResult] = useState<any>(null);
  const [offerings, setOfferings] = useState<any[]>([]);
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [overrideReason, setOverrideReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api("/api/offerings").then(setOfferings); }, []);

  const run = async () => {
    setBusy(true); setError(null); setMessage(null); setEdits({});
    try { setResult(await api("/api/allocation/run", { body: {} })); } catch (e) { setError(errorText(e)); }
    setBusy(false);
  };

  const effective = (sid: number, slot: Slot) => edits[`${sid}:${slot.block_id}`] ?? slot.offering_id;

  const commit = async () => {
    setBusy(true); setError(null);
    const placements: any[] = [];
    for (const s of result.students) {
      for (const slot of s.slots as Slot[]) {
        const oid = effective(s.student_db_id, slot);
        if (!oid) continue;
        const edited = edits[`${s.student_db_id}:${slot.block_id}`] !== undefined;
        const off = offerings.find((o) => o.id === oid);
        const status = edited ? (off && off.seats_left > 0 ? "approved" : "waitlisted")
          : slot.status === "ALLOCATED" ? "approved" : "waitlisted";
        placements.push({ student_id: s.student_db_id, offering_id: oid, status });
      }
    }
    try {
      const r = await api("/api/allocation/commit", { body: { placements, override_reason: overrideReason || null } });
      setMessage(`Committed ${r.committed_students} students (${r.placements} placements). Enrollment counts updated.`);
      setResult(null);
      setOfferings(await api("/api/offerings"));
    } catch (e) { setError(errorText(e)); }
    setBusy(false);
  };

  const editCount = Object.keys(edits).length;

  return (
    <div className="space-y-5">
      <PageHeader title="New Student Allocation" subtitle="Propose placements from remaining seats, review or edit, then commit">
        <button className="btn" onClick={run} disabled={busy}><IconPlay /> {busy ? "Working…" : "Run allocation"}</button>
      </PageHeader>

      <div className="card-tight flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
        <span>① Dry run — nothing is saved</span>
        <span>② Adjust any slot with the dropdowns</span>
        <span>③ Commit to write choices and update enrollment</span>
      </div>

      <ErrorBox error={error} />
      <SuccessBox message={message} />
      {busy && !result && <Spinner label="Allocating…" />}

      {result && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            {Object.entries(result.summary).map(([k, v]: any) => (
              <div key={k} className="card-tight">
                <div className="label">{k.replace(/_/g, " ")}</div>
                <div className="text-xl font-bold tabular-nums text-slate-900">{v}</div>
              </div>
            ))}
          </div>

          {result.students.length === 0 && <div className="card muted">No unallocated NEW students — everyone already has choices.</div>}

          {result.students.map((s: any) => (
            <div key={s.student_db_id} className="card">
              <div className="flex flex-wrap items-center gap-2.5 mb-3">
                <span className="font-mono text-xs bg-slate-100 rounded px-1.5 py-0.5 text-slate-600">{s.student_id}</span>
                <span className="font-semibold text-slate-900">{s.name}</span>
                <Badge status={s.status} />
                <div className="ml-auto"><HlSl hl={s.hl} sl={s.sl} /></div>
              </div>
              {s.warnings.map((w: string, i: number) => <div key={i} className="text-xs text-amber-700 mb-1">⚠ {w}</div>)}
              <div className="overflow-x-auto scroll-thin">
                <table className="tbl">
                  <thead><tr><th className="w-20">Block</th><th className="w-96">Placement (editable)</th><th className="w-32">Status</th><th>Why</th></tr></thead>
                  <tbody>{s.slots.map((slot: Slot) => {
                    const key = `${s.student_db_id}:${slot.block_id}`;
                    const choices = offerings.filter((o) => o.block_id === slot.block_id && o.is_active);
                    const edited = edits[key] !== undefined;
                    return (
                      <tr key={key} className={edited ? "bg-amber-50" : ""}>
                        <td><span className="chip bg-slate-100 text-slate-600 ring-slate-200">{slot.block}</span></td>
                        <td>
                          <select className="input" value={effective(s.student_db_id, slot) ?? ""}
                            onChange={(e) => setEdits({ ...edits, [key]: Number(e.target.value) })}>
                            {choices.map((o) => (
                              <option key={o.id} value={o.id}>
                                {o.subject} {o.level} — {o.seats_left > 0 ? `${o.seats_left} seat${o.seats_left === 1 ? "" : "s"} left` : "FULL"}
                              </option>
                            ))}
                          </select>
                          {edited && <div className="text-[11px] text-amber-700 mt-0.5">Manually changed</div>}
                        </td>
                        <td><Badge status={slot.flag ? "WAITLISTED" : slot.status} />
                          {slot.flag && <div className="text-[10px] font-semibold text-rose-600 mt-0.5">{slot.flag}</div>}</td>
                        <td className="text-xs text-slate-600">{slot.reasons.join(" · ")}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            </div>
          ))}

          <div className="card p-0">
            <div className="p-4 pb-2"><h2 className="h2 mb-0">Seats per offering after this proposal</h2></div>
            <div className="overflow-auto scroll-thin max-h-80">
              <table className="tbl">
                <thead><tr><th>Block</th><th>Subject</th><th>Level</th><th className="text-right">Capacity</th><th className="text-right">Existing</th><th className="text-right">New</th><th className="text-right">Left</th><th className="text-right">Waitlisted</th></tr></thead>
                <tbody>{result.offerings.map((o: any) => (
                  <tr key={o.offering_id}>
                    <td><span className="chip bg-slate-100 text-slate-600 ring-slate-200">{o.block}</span></td>
                    <td className="font-medium">{o.subject}</td><td>{o.level}</td>
                    <td className="text-right tabular-nums">{o.capacity}</td>
                    <td className="text-right tabular-nums text-slate-500">{o.existing_enrollment}</td>
                    <td className="text-right tabular-nums font-semibold text-indigo-600">{o.new_allocated || ""}</td>
                    <td className={`text-right tabular-nums font-semibold ${o.seats_left <= 0 ? "text-rose-600" : "text-emerald-600"}`}>{o.seats_left}</td>
                    <td className="text-right tabular-nums text-amber-600">{o.waitlisted || ""}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>

          {result.students.length > 0 && (
            <div className="card flex flex-wrap items-end gap-3 sticky bottom-4 shadow-lg">
              <AdminOnly>
                <div className="flex-1 min-w-64">
                  <label className="label">Override reason (only needed if manual edits break rules or capacity)</label>
                  <input className="input" placeholder="e.g. Head of School approved an extra seat in Chemistry HL"
                    value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} />
                </div>
                <div className="flex items-center gap-3">
                  {editCount > 0 && <span className="chip bg-amber-50 text-amber-700 ring-amber-200">{editCount} manual edit{editCount === 1 ? "" : "s"}</span>}
                  <button className="btn" onClick={commit} disabled={busy}><IconSave /> Commit allocation</button>
                </div>
              </AdminOnly>
            </div>
          )}
        </>
      )}

      {!result && !busy && !message && (
        <div className="card text-center py-10">
          <IconCheck className="w-10 h-10 mx-auto text-slate-300" />
          <p className="muted mt-2">Click <b>Run allocation</b> to generate a proposal for all NEW students.</p>
        </div>
      )}
    </div>
  );
}
