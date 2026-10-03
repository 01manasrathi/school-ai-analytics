"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, errorText } from "@/lib/api";
import { ErrorBox, PageHeader, Spinner, Stat } from "@/components/ui";
import { IconGrid, IconPlay, IconSwap, IconUserPlus, IconWarning } from "@/components/icons";

export default function Dashboard() {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api("/api/dashboard").then(setD).catch((e) => setError(errorText(e))); }, []);

  if (error) return <ErrorBox error={error} />;
  if (!d) return <Spinner />;

  const pct = d.total_capacity ? Math.round((d.total_enrolled / d.total_capacity) * 100) : 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Grade 11 IBDP option allocation at a glance">
        <Link href="/new-allocation" className="btn"><IconPlay /> Run allocation</Link>
        <Link href="/change-requests" className="btn-secondary"><IconSwap /> Change requests</Link>
      </PageHeader>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Existing students" value={d.students.existing} sub="returning, already allocated" icon={<IconGrid className="w-7 h-7" />} />
        <Stat label="New students" value={d.students.new} tone="indigo" sub="to allocate from remaining seats" icon={<IconUserPlus className="w-7 h-7" />} />
        <Stat label="Seats used" value={`${d.total_enrolled}/${d.total_capacity}`} tone="emerald" sub={`${pct}% of capacity · ${d.offerings} offerings`} />
        <Stat label="Pending changes" value={d.pending_change_requests} tone="sky" sub="awaiting a decision" icon={<IconSwap className="w-7 h-7" />} />
        <Stat label="Full classes" value={d.full_classes.length} tone="amber" sub="at or over capacity" />
        <Stat label="Waitlist entries" value={d.waitlist_count} tone="amber" />
        <Stat label="Unallocated new students" value={d.unallocated_new_students.length} tone="rose" sub="no or partial placement" />
        <Stat label="Below minimum" value={d.below_min_classes.length} tone="slate" sub="classes under min enrollment" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="h2">Full / over-capacity classes</h2>
          {d.full_classes.length === 0 ? <p className="muted">Nothing is full — every class still has seats.</p> : (
            <div className="max-h-72 overflow-auto scroll-thin -mx-2 px-2">
              <table className="tbl">
                <thead><tr><th>Block</th><th>Subject</th><th>Level</th><th className="text-right">Enrolled</th></tr></thead>
                <tbody>{d.full_classes.map((o: any) => (
                  <tr key={o.id}>
                    <td><span className="chip bg-slate-100 text-slate-600 ring-slate-200">{o.block}</span></td>
                    <td className="font-medium">{o.subject}</td>
                    <td>{o.level}</td>
                    <td className={`text-right tabular-nums font-semibold ${o.over_capacity ? "text-rose-600" : "text-amber-600"}`}>{o.current_enrollment}/{o.capacity}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="h2">New students needing attention</h2>
          {d.unallocated_new_students.length === 0 ? <p className="muted">All new students are fully allocated.</p> : (
            <>
              <div className="max-h-60 overflow-auto scroll-thin -mx-2 px-2">
                <table className="tbl">
                  <thead><tr><th>ID</th><th>Name</th><th className="text-right">Approved choices</th></tr></thead>
                  <tbody>{d.unallocated_new_students.map((s: any) => (
                    <tr key={s.id}><td className="font-mono text-xs">{s.student_id}</td><td className="font-medium">{s.name}</td>
                      <td className="text-right tabular-nums">{s.approved_choices}/7</td></tr>
                  ))}</tbody>
                </table>
              </div>
              <Link href="/new-allocation" className="btn mt-3"><IconPlay /> Run allocation</Link>
            </>
          )}
        </div>

        <div className="card lg:col-span-2">
          <h2 className="h2 flex items-center gap-2"><IconWarning className="w-4 h-4 text-sky-500" /> Classes below minimum enrollment ({d.below_min_classes.length})</h2>
          {d.below_min_classes.length === 0 ? <p className="muted">All classes meet their minimum.</p> : (
            <div className="flex flex-wrap gap-1.5">
              {d.below_min_classes.map((o: any) => (
                <span key={o.id} className="chip bg-sky-50 text-sky-800 ring-sky-200 px-2 py-1">
                  {o.block} · {o.subject} {o.level} <b className="tabular-nums">{o.current_enrollment}/{o.min_enrollment}</b>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
