"use client";
import { useEffect, useState } from "react";
import { api, auth, errorText } from "@/lib/api";
import { AdminOnly, ErrorBox, PageHeader, SuccessBox } from "@/components/ui";
import { IconCheck, IconDownload, IconUpload } from "@/components/icons";

const TYPES: [string, string][] = [
  ["blocks", "Option blocks"], ["subjects", "Subjects"], ["offerings", "Subject offerings"], ["students", "Students"],
  ["choices", "Existing choices"], ["preferences", "New-student preferences"], ["change_requests", "Change requests"],
];

export default function ImportPage() {
  const [type, setType] = useState("students");
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any>(null);
  const [specs, setSpecs] = useState<any>({});
  const [skipInvalid, setSkipInvalid] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api("/api/import/specs").then(setSpecs); }, []);
  useEffect(() => { setResult(null); setMapping({}); setError(null); }, [type, file]);

  const send = async (dryRun: boolean, useMapping: boolean) => {
    if (!file) return;
    setError(null); setBusy(true);
    const form = new FormData();
    form.append("type", type);
    form.append("file", file);
    form.append("dry_run", String(dryRun));
    form.append("skip_invalid", String(skipInvalid));
    if (useMapping) form.append("mapping", JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([, v]) => v))));
    try {
      const r = await api("/api/import/csv", { form });
      setResult(r);
      if (!useMapping) setMapping(Object.fromEntries(r.headers.map((h: string) => [h, r.mapping[h] || ""])));
    } catch (e) { setError(errorText(e)); }
    setBusy(false);
  };

  const downloadTemplate = async () => {
    const res = await fetch(`/api/import/templates/${type}`, { headers: { Authorization: `Bearer ${auth.token()}` } });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob());
    a.download = `${type}_template.csv`;
    a.click();
  };

  const spec = specs[type];
  return (
    <div className="space-y-5">
      <PageHeader title="Import CSV" subtitle="Validate first (dry run), fix the column mapping, then import" />

      <div className="card-tight text-sm text-slate-600">
        Recommended order: <b>blocks → subjects → offerings → students → existing choices → preferences → change requests</b>.
        Rows are matched on their natural key, so re-importing a file updates instead of duplicating.
      </div>

      <div className="card space-y-4">
        <div className="grid md:grid-cols-3 gap-3 items-end">
          <div>
            <label className="label">Data type</label>
            <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="label">CSV file</label>
            <input className="input file:mr-2 file:rounded file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-xs file:font-semibold"
              type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </div>
          <button className="btn-secondary" onClick={downloadTemplate}><IconDownload /> Download template</button>
        </div>

        {spec && (
          <div className="rounded-lg bg-slate-50 ring-1 ring-slate-200 p-3 text-xs text-slate-600 space-y-1">
            <div className="flex flex-wrap gap-1.5">
              {spec.fields.map((f: string) => (
                <code key={f} className={`rounded px-1.5 py-0.5 ring-1 ${spec.required.includes(f) ? "bg-white text-slate-900 font-bold ring-slate-300" : "bg-white/60 text-slate-500 ring-slate-200"}`}>{f}</code>
              ))}
            </div>
            <div className="text-slate-400">Bold columns are required.</div>
            {type === "preferences" && <div>Preference format: <code>SUBJECT_CODE:HL</code>, <code>SUBJECT_CODE:SL</code>, or just <code>SUBJECT_CODE</code>.</div>}
          </div>
        )}

        <AdminOnly>
          <button className="btn" disabled={!file || busy} onClick={() => send(true, false)}>
            <IconCheck /> {busy ? "Validating…" : "1 · Validate (dry run)"}
          </button>
        </AdminOnly>
      </div>

      <ErrorBox error={error} />

      {result && (
        <div className="grid lg:grid-cols-2 gap-4 items-start">
          <div className="card">
            <h2 className="h2">Column mapping</h2>
            <table className="tbl">
              <thead><tr><th>CSV column</th><th>Maps to field</th></tr></thead>
              <tbody>{result.headers.map((h: string) => (
                <tr key={h}>
                  <td className="font-mono text-xs">{h}</td>
                  <td>
                    <select className="input" value={mapping[h] || ""} onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}>
                      <option value="">— ignore —</option>
                      {result.expected_fields.map((f: string) => (
                        <option key={f} value={f}>{f}{result.required_fields.includes(f) ? " *" : ""}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}</tbody>
            </table>
            <button className="btn-secondary mt-3" onClick={() => send(true, true)}>Re-validate with this mapping</button>
          </div>

          <div className="card space-y-3">
            <h2 className="h2 mb-0">Validation result</h2>
            <div className="grid grid-cols-3 gap-2">
              {[["Rows", result.total_rows, "text-slate-900"], ["Valid", result.valid_rows, "text-emerald-600"], ["Errors", result.errors.length, "text-rose-600"]].map(([l, v, c]: any) => (
                <div key={l} className="rounded-lg bg-slate-50 ring-1 ring-slate-200 px-3 py-2">
                  <div className="label mb-0">{l}</div><div className={`text-xl font-bold tabular-nums ${c}`}>{v}</div>
                </div>
              ))}
            </div>
            {result.committed && <SuccessBox message={`Imported: ${result.created} created, ${result.updated} updated.`} />}
            {result.errors.length > 0 && (
              <div className="max-h-56 overflow-auto scroll-thin">
                <table className="tbl">
                  <thead><tr><th className="w-16">Row</th><th>Error</th></tr></thead>
                  <tbody>{result.errors.map((e: any, i: number) => (
                    <tr key={i}><td className="tabular-nums">{e.row}</td><td className="text-rose-700 text-xs">{e.message}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {result.preview.length > 0 && (
              <details>
                <summary className="text-sm cursor-pointer text-indigo-700">Preview first rows (after mapping)</summary>
                <pre className="mt-2 text-xs bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto scroll-thin">{JSON.stringify(result.preview, null, 2)}</pre>
              </details>
            )}
            {!result.committed && (
              <AdminOnly>
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" className="rounded border-slate-300" checked={skipInvalid} onChange={(e) => setSkipInvalid(e.target.checked)} />
                    Skip invalid rows
                  </label>
                  <button className="btn" disabled={busy || (result.errors.length > 0 && !skipInvalid)} onClick={() => send(false, true)}>
                    <IconUpload /> 2 · Import
                  </button>
                  {result.errors.length > 0 && !skipInvalid && <span className="text-xs text-slate-500">Fix the errors or tick “skip invalid rows”.</span>}
                </div>
              </AdminOnly>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
