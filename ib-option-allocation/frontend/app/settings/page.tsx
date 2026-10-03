"use client";
import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { AdminOnly, ErrorBox, PageHeader, SuccessBox } from "@/components/ui";
import { IconPlus, IconRefresh, IconSave, IconX } from "@/components/icons";

type Tab = "rules" | "offerings" | "blocks";
const TABS: [Tab, string][] = [["rules", "IB rules"], ["offerings", "Capacities / offerings"], ["blocks", "Block structure"]];

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("rules");
  const [rules, setRules] = useState<any[]>([]);
  const [ruleTypes, setRuleTypes] = useState<Record<string, string>>({});
  const [offerings, setOfferings] = useState<any[]>([]);
  const [blocks, setBlocks] = useState<any[]>([]);
  const [programmes, setProgrammes] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    api("/api/rules").then((r) => {
      setRules(r.rules.map((x: any) => ({ ...x, conditionText: JSON.stringify(x.condition) })));
      setRuleTypes(r.rule_types);
    });
    api("/api/offerings").then(setOfferings);
    api("/api/blocks").then(setBlocks);
    api("/api/programmes").then(setProgrammes);
  };
  useEffect(load, []);

  const run = async (fn: () => Promise<any>, ok: string) => {
    setError(null); setMsg(null);
    try { await fn(); setMsg(ok); load(); } catch (e) { setError(errorText(e)); }
  };

  const saveRule = (r: any) => run(async () => {
    let condition;
    try { condition = JSON.parse(r.conditionText || "{}"); } catch { throw new Error("Condition must be valid JSON"); }
    const body = { programme_id: r.programme_id, rule_type: r.rule_type, condition, value: r.value,
      priority: Number(r.priority), is_active: r.is_active, description: r.description };
    return r.id ? api(`/api/rules/${r.id}`, { method: "PUT", body }) : api("/api/rules", { body });
  }, "Rule saved — it applies immediately to feasibility checks and allocation");

  const setRule = (i: number, patch: any) => setRules(rules.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const setOff = (id: number, patch: any) => setOfferings(offerings.map((o) => (o.id === id ? { ...o, ...patch } : o)));
  const setBlk = (id: number, patch: any) => setBlocks(blocks.map((b) => (b.id === id ? { ...b, ...patch } : b)));

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" subtitle="Every IB rule, capacity and block lives in the database — nothing is hardcoded">
        <AdminOnly>
          <button className="btn-secondary" onClick={() => run(() => api("/api/admin/recompute-enrollment", { body: {} }), "Enrollment recomputed from approved choices")}>
            <IconRefresh /> Recompute enrollment
          </button>
        </AdminOnly>
      </PageHeader>

      <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        {TABS.map(([t, label]) => (
          <button key={t} className={`tab ${tab === t ? "tab-active" : ""}`} onClick={() => setTab(t)}>{label}</button>
        ))}
      </div>

      <ErrorBox error={error} />
      <SuccessBox message={msg} />

      {tab === "rules" && (
        <div className="card p-0">
          <p className="px-4 pt-4 text-xs text-slate-500">
            <code>condition</code> is JSON. <code>severity</code> may be <code>NEEDS_OVERRIDE</code> (admin can force) or <code>NOT_FEASIBLE</code> (blocked).
            Untick <b>Active</b> to switch a rule off entirely.
          </p>
          <div className="overflow-x-auto scroll-thin mt-2">
            <table className="tbl">
              <thead><tr><th className="w-16">Active</th><th>Type</th><th className="w-20">Value</th><th className="min-w-80">Condition (JSON)</th><th className="w-20">Priority</th><th>Description</th><th /></tr></thead>
              <tbody>{rules.map((r, i) => (
                <tr key={r.id ?? `new-${i}`} className={r.is_active ? "" : "opacity-50"}>
                  <td><input type="checkbox" className="rounded border-slate-300" checked={r.is_active} onChange={(e) => setRule(i, { is_active: e.target.checked })} /></td>
                  <td>
                    <select className="input" value={r.rule_type} onChange={(e) => setRule(i, { rule_type: e.target.value })}>
                      {Object.keys(ruleTypes).map((t) => <option key={t}>{t}</option>)}
                    </select>
                    <div className="text-[10px] text-slate-500 max-w-xs mt-0.5">{ruleTypes[r.rule_type]}</div>
                  </td>
                  <td><input className="input" value={r.value} onChange={(e) => setRule(i, { value: e.target.value })} /></td>
                  <td><input className="input font-mono text-[11px]" value={r.conditionText} onChange={(e) => setRule(i, { conditionText: e.target.value })} /></td>
                  <td><input className="input" type="number" value={r.priority} onChange={(e) => setRule(i, { priority: e.target.value })} /></td>
                  <td><input className="input" value={r.description} onChange={(e) => setRule(i, { description: e.target.value })} /></td>
                  <td className="whitespace-nowrap">
                    <AdminOnly>
                      <div className="flex gap-1">
                        <button className="btn btn-xs" onClick={() => saveRule(r)}><IconSave className="w-3 h-3" /> Save</button>
                        {r.id && <button className="btn-secondary btn-xs" title="Delete rule"
                          onClick={() => confirm("Delete this rule?") && run(() => api(`/api/rules/${r.id}`, { method: "DELETE" }), "Rule deleted")}><IconX className="w-3 h-3" /></button>}
                      </div>
                    </AdminOnly>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="p-4">
            <AdminOnly>
              <button className="btn-secondary" onClick={() => setRules([...rules, {
                programme_id: programmes.find((p) => p.name === "IBDP")?.id ?? null, rule_type: "REQUIRED_CATEGORY", value: "1",
                conditionText: '{"name": "New category", "groups": [], "subject_codes": [], "severity": "NEEDS_OVERRIDE"}',
                priority: 100, is_active: true, description: "" }])}>
                <IconPlus /> Add rule
              </button>
            </AdminOnly>
          </div>
        </div>
      )}

      {tab === "offerings" && (
        <div className="card p-0 overflow-auto scroll-thin max-h-[70vh]">
          <table className="tbl">
            <thead><tr><th>Block</th><th>Subject</th><th>Level</th><th>Teacher</th><th>Room</th><th className="w-24">Capacity</th><th className="w-20">Min</th><th className="w-20">Enrolled</th><th className="w-16">Active</th><th /></tr></thead>
            <tbody>{offerings.map((o) => (
              <tr key={o.id} className={o.is_active ? "" : "opacity-50"}>
                <td>
                  <select className="input w-16" value={o.block_id} onChange={(e) => setOff(o.id, { block_id: Number(e.target.value) })}>
                    {blocks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </td>
                <td className="font-medium whitespace-nowrap">{o.subject}</td>
                <td><span className={`chip ${o.level === "HL" ? "bg-indigo-50 text-indigo-700 ring-indigo-200" : "bg-teal-50 text-teal-700 ring-teal-200"}`}>{o.level}</span></td>
                <td><input className="input" value={o.teacher} onChange={(e) => setOff(o.id, { teacher: e.target.value })} /></td>
                <td><input className="input w-24" value={o.room} onChange={(e) => setOff(o.id, { room: e.target.value })} /></td>
                <td><input className="input" type="number" value={o.capacity} onChange={(e) => setOff(o.id, { capacity: Number(e.target.value) })} /></td>
                <td><input className="input" type="number" value={o.min_enrollment} onChange={(e) => setOff(o.id, { min_enrollment: Number(e.target.value) })} /></td>
                <td className={`tabular-nums font-semibold ${o.over_capacity ? "text-rose-600" : o.full ? "text-amber-600" : "text-slate-700"}`}>{o.current_enrollment}</td>
                <td><input type="checkbox" className="rounded border-slate-300" checked={o.is_active} onChange={(e) => setOff(o.id, { is_active: e.target.checked })} /></td>
                <td>
                  <AdminOnly>
                    <button className="btn btn-xs" onClick={() => run(() => api(`/api/offerings/${o.id}`, { method: "PUT", body: {
                      block_id: o.block_id, teacher: o.teacher, room: o.room, capacity: o.capacity,
                      min_enrollment: o.min_enrollment, is_active: o.is_active } }), "Offering saved")}>
                      <IconSave className="w-3 h-3" /> Save
                    </button>
                  </AdminOnly>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {tab === "blocks" && (
        <div className="card p-0">
          <p className="px-4 pt-4 text-xs text-slate-500">
            Blocks are data, not code: add, rename or re-order them here. Blocks sharing the same <code>period</code> count as a timetable clash for a student.
          </p>
          <div className="overflow-x-auto scroll-thin mt-2">
            <table className="tbl">
              <thead><tr><th className="w-20">Name</th><th>Label</th><th>Programme</th><th className="w-24">Grade(s)</th><th className="w-28">Period</th><th className="w-24">Max/student</th><th className="w-20">Order</th><th>Notes</th><th /></tr></thead>
              <tbody>{blocks.map((b) => (
                <tr key={b.id}>
                  <td><input className="input" value={b.name} onChange={(e) => setBlk(b.id, { name: e.target.value })} /></td>
                  <td><input className="input" value={b.label} onChange={(e) => setBlk(b.id, { label: e.target.value })} /></td>
                  <td className="text-sm">{b.programme}</td>
                  <td><input className="input" value={b.grade} onChange={(e) => setBlk(b.id, { grade: e.target.value })} /></td>
                  <td><input className="input" value={b.period} onChange={(e) => setBlk(b.id, { period: e.target.value })} /></td>
                  <td><input className="input" type="number" value={b.max_choices_per_student} onChange={(e) => setBlk(b.id, { max_choices_per_student: Number(e.target.value) })} /></td>
                  <td><input className="input" type="number" value={b.sort_order} onChange={(e) => setBlk(b.id, { sort_order: Number(e.target.value) })} /></td>
                  <td><input className="input" value={b.notes} onChange={(e) => setBlk(b.id, { notes: e.target.value })} /></td>
                  <td className="whitespace-nowrap">
                    <AdminOnly>
                      <div className="flex gap-1">
                        <button className="btn btn-xs" onClick={() => run(() => api(b.id > 0 ? `/api/blocks/${b.id}` : "/api/blocks", {
                          method: b.id > 0 ? "PUT" : "POST",
                          body: { name: b.name, label: b.label, programme_id: b.programme_id, grade: b.grade, period: b.period,
                            max_choices_per_student: b.max_choices_per_student, sort_order: b.sort_order, notes: b.notes } }), "Block saved")}>
                          <IconSave className="w-3 h-3" /> Save
                        </button>
                        {b.id > 0 && <button className="btn-secondary btn-xs" title="Delete block"
                          onClick={() => confirm("Delete this block?") && run(() => api(`/api/blocks/${b.id}`, { method: "DELETE" }), "Block deleted")}><IconX className="w-3 h-3" /></button>}
                      </div>
                    </AdminOnly>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="p-4">
            <AdminOnly>
              <button className="btn-secondary" onClick={() => {
                const p = programmes.find((x) => x.name === "IBDP") || programmes[0];
                setBlocks([...blocks, { id: -Date.now(), name: "H", label: "", programme_id: p?.id, programme: p?.name,
                  grade: "11-12", period: "", max_choices_per_student: 1, sort_order: blocks.length + 1, notes: "" }]);
              }}><IconPlus /> Add block</button>
            </AdminOnly>
          </div>
        </div>
      )}
    </div>
  );
}
