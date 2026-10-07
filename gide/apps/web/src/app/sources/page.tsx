"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";
import { Btn, Card, ErrorBox, NeedCourse } from "@/components/Shell";
import { SourceViewer, ViewTarget } from "@/components/SourceViewer";
import { fmtTs, Source, Unit } from "@/lib/types";

const unitWhere = (u: Unit) => u.page_number ? `p.${u.page_number}` : u.slide_number ? `slide ${u.slide_number}` : u.time_start != null ? `${fmtTs(u.time_start)}–${fmtTs(u.time_end ?? u.time_start)}` : "";
const pill = (s: string) => ({ completed: "bg-emerald-500/15 text-emerald-300", failed: "bg-red-500/15 text-red-300", processing: "bg-amber-500/15 text-amber-300", queued: "bg-zinc-700 text-zinc-300" } as Record<string, string>)[s] ?? "bg-zinc-700";

function Sources({ courseId }: { courseId: string }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [sel, setSel] = useState<Source | null>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [target, setTarget] = useState<ViewTarget | null>(null);
  const [filter, setFilter] = useState("all");
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try { setSources(await api<Source[]>(`/api/sources?course_id=${courseId}`)); } catch (e: any) { setErr(e.message); }
  }, [courseId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!sources.some((s) => s.status === "queued" || s.status === "processing")) return;
    const t = setInterval(load, 2000); return () => clearInterval(t);
  }, [sources, load]);

  const open = async (s: Source) => {
    setSel(s); setTarget(null); setFilter("all");
    setUnits(await api<Unit[]>(`/api/sources/${s.id}/units`));
  };
  const show = (u: Unit) => sel && setTarget({ source_id: sel.id, source_type: sel.source_type, title: sel.title, media_url: sel.media_url ?? "",
    page: u.page_number, slide: u.slide_number, time_start: u.time_start, image_path: u.unit_type === "diagram" || u.unit_type === "keyframe" ? u.image_path : (sel.source_type === "pptx" ? u.image_path : null), note: u.content.slice(0, 300) });

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true); setErr(null);
    for (const f of Array.from(files)) {
      const fd = new FormData(); fd.append("file", f); fd.append("course_id", courseId);
      try { await api("/api/sources/upload", { method: "POST", body: fd }); } catch (e: any) { setErr(`${f.name}: ${e.message}`); }
    }
    setBusy(false); if (file.current) file.current.value = ""; load();
  };
  const build = async () => {
    setErr(null); setInfo(null);
    try { const r = await post(`/api/courses/${courseId}/build-knowledge`, {}); setInfo(r.warning + " Building runs in the background; check the Knowledge map page when done."); } catch (e: any) { setErr(e.message); }
  };

  const shown = units.filter((u) => filter === "all" || (filter === "visual" ? ["diagram", "keyframe", "image", "slide"].includes(u.unit_type) : u.unit_type === filter || (filter === "text" && u.unit_type === "heading")));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Sources</h1><p className="text-sm text-zinc-400">PDF, PPTX, video and images. Every extracted unit keeps its page, slide or timestamp.</p></div>
        <div className="flex gap-2">
          <input ref={file} type="file" multiple accept=".pdf,.pptx,.mp4,.webm,.mov,.mkv,.png,.jpg,.jpeg,.webp" hidden onChange={(e) => upload(e.target.files)} />
          <Btn onClick={() => file.current?.click()} disabled={busy}>{busy ? "Uploading…" : "Upload files"}</Btn>
          <Btn tone="ghost" onClick={build}>Build knowledge base</Btn>
        </div>
      </div>
      <ErrorBox msg={err} />
      {info && <div className="rounded-lg border border-emerald-900 bg-emerald-950/40 p-3 text-sm text-emerald-300">{info}</div>}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sources.map((s) => {
          const j = s.processing_jobs[0]; const w: string[] = s.source_metadata?.warnings ?? [];
          return (
            <Card key={s.id} className={`cursor-pointer ${sel?.id === s.id ? "ring-1 ring-emerald-500/60" : ""}`}>
              <div onClick={() => open(s)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0"><div className="truncate font-medium">{s.title}</div><div className="text-xs uppercase text-zinc-500">{s.source_type} · {(s.file_size_bytes / 1e6).toFixed(1)} MB</div></div>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${pill(s.status)}`}>{s.status}</span>
                </div>
                {(s.status === "processing" || s.status === "queued") && j && (
                  <div className="mt-3"><div className="h-1.5 overflow-hidden rounded bg-zinc-800"><div className="h-full bg-emerald-500 transition-all" style={{ width: `${j.progress_percent}%` }} /></div><div className="mt-1 text-xs text-zinc-500">{j.stage.replaceAll("_", " ")}</div></div>
                )}
                {s.status === "completed" && <div className="mt-2 text-xs text-zinc-400">{s.source_metadata.unit_count} units{s.source_metadata.asr_engine ? ` · transcript: ${s.source_metadata.asr_engine}` : ""}{s.source_metadata.vision_done != null ? ` · vision ${s.source_metadata.vision_done}/${s.source_metadata.vision_attempted}` : ""}</div>}
                {s.error_message && <div className="mt-2 break-words text-xs text-red-300">{s.error_message}</div>}
                {w.map((x, i) => <div key={i} className="mt-1 text-xs text-amber-300">⚠ {x}</div>)}
              </div>
              <div className="mt-3 flex gap-2">
                {(s.status === "failed" || s.status === "completed") && <Btn tone="ghost" className="!px-2 !py-1 text-xs" onClick={async () => { try { await post(`/api/sources/${s.id}/retry`, {}); load(); } catch (e: any) { setErr(e.message); } }}>Retry</Btn>}
                <Btn tone="ghost" className="!px-2 !py-1 text-xs" onClick={async () => { if (confirm("Delete this source?")) { await api(`/api/sources/${s.id}`, { method: "DELETE" }); if (sel?.id === s.id) { setSel(null); setUnits([]); setTarget(null); } load(); } }}>Delete</Btn>
              </div>
            </Card>
          );
        })}
        {sources.length === 0 && <p className="text-sm text-zinc-500">No sources yet. Upload a textbook PDF, slide deck or lecture video.</p>}
      </div>

      {sel && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 flex gap-1 text-xs">{["all", "text", "visual", "caption"].map((f) => <button key={f} onClick={() => setFilter(f)} className={`rounded-md px-2 py-1 ${filter === f ? "bg-zinc-700" : "bg-zinc-900 text-zinc-400"}`}>{f}</button>)}<span className="ml-auto text-zinc-500">{shown.length} units</span></div>
            <div className="max-h-[600px] space-y-2 overflow-y-auto pr-1">
              {shown.map((u) => (
                <button key={u.id} onClick={() => show(u)} className="block w-full rounded-xl border border-zinc-800 bg-zinc-900/40 p-3 text-left hover:border-zinc-600">
                  <div className="mb-1 flex items-center gap-2 text-[11px]"><span className="rounded bg-zinc-800 px-1.5 py-0.5 uppercase text-zinc-300">{u.unit_type}</span><span className="text-emerald-400">{unitWhere(u)}</span>{u.unit_metadata?.ocr_engine && <span className="text-zinc-500">OCR/vision</span>}</div>
                  <p className="line-clamp-3 text-sm text-zinc-300">{u.content}</p>
                </button>
              ))}
            </div>
          </div>
          <SourceViewer target={target} onClose={() => setTarget(null)} />
        </div>
      )}
    </div>
  );
}

export default function Page() { return <NeedCourse>{(id) => <Sources courseId={id} />}</NeedCourse>; }
