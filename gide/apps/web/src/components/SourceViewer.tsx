"use client";
import React, { useEffect, useRef, useState } from "react";
import { API } from "@/lib/api";
import { fmtTs } from "@/lib/types";

/** Where to open. Built from a ContentUnit (sources page) or a Citation (tutor/assessments). */
export interface ViewTarget {
  source_id: string; source_type: string; title: string; media_url: string;
  page?: number | null; slide?: number | null; time_start?: number | null; image_path?: string | null;
  note?: string;
}

export function SourceViewer({ target, onClose }: { target: ViewTarget | null; onClose?: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => { setImgFailed(false); }, [target?.source_id, target?.slide, target?.image_path]);
  useEffect(() => {
    const v = video.current;
    if (!v || target?.time_start == null) return;
    const seek = () => { v.currentTime = target.time_start as number; };
    if (v.readyState >= 1) seek(); else v.addEventListener("loadedmetadata", seek, { once: true });
  }, [target?.source_id, target?.time_start]);

  if (!target) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">
        Click a citation or a content unit to open the exact page, slide or timestamp here.
      </div>
    );
  }
  const raw = `${API}${target.media_url}`;
  const where = target.page ? `Page ${target.page}` : target.slide ? `Slide ${target.slide}` : target.time_start != null ? `Timestamp ${fmtTs(target.time_start)}` : "";
  const slideImg = target.image_path ? `${API}/storage/${target.image_path}` : `${API}/storage/slides/${target.source_id}/slide_${target.slide}.png`;

  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-900/70 px-4 py-2.5">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-zinc-100">{target.title}</div>
          <div className="text-xs text-emerald-400">{where}</div>
        </div>
        <div className="flex items-center gap-2">
          <a href={target.source_type === "pdf" && target.page ? `${raw}#page=${target.page}` : raw} target="_blank" rel="noreferrer" className="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">Open raw</a>
          {onClose && <button onClick={onClose} className="rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800">✕</button>}
        </div>
      </div>
      <div className="min-h-[420px] bg-zinc-900/30">
        {target.source_type === "pdf" && (
          <iframe key={`${target.source_id}-${target.page}`} src={`${raw}#page=${target.page ?? 1}`} className="h-[560px] w-full border-0" title="PDF viewer" />
        )}
        {target.source_type === "pptx" && (imgFailed ? (
          <div className="p-6 text-sm text-amber-300">The slide image was not rendered for this deck (LibreOffice missing or failed during ingestion). Check the source's warnings on the Sources page.</div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={slideImg} alt={`Slide ${target.slide}`} onError={() => setImgFailed(true)} className="mx-auto max-h-[560px] object-contain p-3" />
        ))}
        {target.source_type === "video" && (
          <video ref={video} key={target.source_id} src={raw} controls className="max-h-[560px] w-full bg-black" />
        )}
        {target.source_type === "image" && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={raw} alt={target.title} className="mx-auto max-h-[560px] object-contain p-3" />
        )}
      </div>
      {target.note && <div className="border-t border-zinc-800 p-3 text-xs leading-relaxed text-zinc-400">“{target.note}”</div>}
    </div>
  );
}
