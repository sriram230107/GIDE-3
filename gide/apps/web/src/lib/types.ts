export interface Course { id: string; title: string; code?: string | null }
export interface Job { id: string; state: string; stage: string; progress_percent: number; attempt_number: number; error_detail?: any }
export interface Source {
  id: string; course_id: string; title: string; source_type: "pdf" | "pptx" | "video" | "image";
  file_size_bytes: number; status: string; error_message?: string | null;
  source_metadata: Record<string, any>; processing_jobs: Job[]; media_url?: string | null;
}
export interface Unit {
  id: string; source_id: string; source_type: string; unit_type: string; content: string;
  vision_caption?: string | null; ocr_text?: string | null; page_number?: number | null; slide_number?: number | null;
  time_start?: number | null; time_end?: number | null; image_path?: string | null;
  bounding_box?: { x0: number; y0: number; x1: number; y1: number } | null; sequence_index: number;
  unit_metadata?: Record<string, any>;
}
/** One citation = one ContentUnit location. Everything that opens a source uses this shape. */
export interface Citation {
  n: number; unit_id: string; source_id: string; source_title: string; source_type: string; media_url: string;
  page?: number | null; slide?: number | null; time_start?: number | null; time_end?: number | null;
  image_path?: string | null; snippet: string; chunk_id?: string;
}
export interface ConceptStat {
  id: string; name: string; topic_id: string | null; topic: string | null; p: number; eff: number; risk: number;
  attempts: number; correct: number; practised: boolean; prior_source: string; prereq_ids: string[]; dependent_ids: string[];
}
export const fmtTs = (t: number) => {
  const s = Math.floor(t);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const mm = String(m).padStart(2, "0"), ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};
export const citeLabel = (c: Citation) =>
  c.page ? `${c.source_title} · p.${c.page}` : c.slide ? `${c.source_title} · slide ${c.slide}`
  : c.time_start != null ? `${c.source_title} · ${fmtTs(c.time_start)}` : c.source_title;
