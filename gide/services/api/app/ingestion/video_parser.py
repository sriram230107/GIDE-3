"""Video ingestion: ffmpeg audio -> faster-whisper segments (primary ASR, no silent fallback)
+ OpenCV scene-change keyframes (HSV histogram distance).

Why faster-whisper is primary: citations must open the exact timestamp, and forced-alignment style ASR gives
segment timestamps that are reliably tied to the audio, unlike LLM-generated timestamps. Gemini is used only
for the vision pass on keyframes. The engine used is recorded in source metadata and shown in the UI.
"""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional
from uuid import UUID


def fmt_ts(t: float) -> str:
    t = int(t)
    return f"{t // 3600:d}:{(t % 3600) // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def find_ffmpeg() -> str:
    p = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not p:
        raise RuntimeError("ffmpeg not found on PATH (needed to extract audio)")
    return p


def extract_audio(video_path: str, wav_path: str) -> None:
    cmd = [find_ffmpeg(), "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", wav_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {r.stderr[-400:]}")


def has_audio_stream(video_path: str) -> bool:
    ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ffprobe:
        return True  # let ffmpeg report the real error
    r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", video_path], capture_output=True, text=True)
    return bool(r.stdout.strip())


def transcribe(wav_path: str, model_size: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # visible failure, never a fake transcript
        raise RuntimeError("faster-whisper is not installed (pip install faster-whisper)") from e
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, info = model.transcribe(wav_path, vad_filter=True)
    out = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in segs if s.text.strip()]
    return out, {"asr_engine": f"faster-whisper:{model_size}", "language": info.language,
                 "language_probability": round(float(info.language_probability), 3)}


def group_segments(segments: list[dict[str, Any]], max_len: float = 30.0, max_gap: float = 2.0) -> list[dict[str, Any]]:
    """Merge consecutive ASR segments into caption units of at most max_len seconds."""
    groups: list[dict[str, Any]] = []
    for s in segments:
        g = groups[-1] if groups else None
        if g and (s["start"] - g["end"]) <= max_gap and (s["end"] - g["start"]) <= max_len:
            g["end"] = s["end"]
            g["text"] += " " + s["text"]
        else:
            groups.append({"start": s["start"], "end": s["end"], "text": s["text"]})
    return groups


def _hist(frame):
    import cv2
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    cv2.normalize(h, h, alpha=1.0, norm_type=cv2.NORM_L1)
    return h


def detect_keyframes(video_path: str, out_dir: Path, threshold: float = 0.35, sample_fps: float = 1.0,
                     max_gap: float = 30.0, dedupe: float = 0.10, max_count: int = 80) -> tuple[list[tuple[float, str]], dict[str, Any]]:
    """Return ([(timestamp, filename)], stats).

    A frame becomes a keyframe when its Bhattacharyya histogram distance from the LAST keyframe exceeds
    `threshold`. A forced keyframe is added after `max_gap` seconds without one, unless the picture is
    unchanged (distance < dedupe). Keyframes near-identical to ANY earlier keyframe are dropped. If more than
    `max_count` remain they are subsampled evenly (caps vision calls). Stats are returned for the audit log."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("OpenCV could not open the video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = n_frames / fps if fps else 0.0
    step = max(1, int(round(fps / sample_fps)))
    out_dir.mkdir(parents=True, exist_ok=True)

    kept: list[tuple[float, Any, Any]] = []  # (ts, hist, frame)
    last_hist, last_ts = None, 0.0
    scene_hits = forced_hits = dropped_dupes = 0
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                ts = idx / fps
                h = _hist(frame)
                if last_hist is None:
                    kept.append((ts, h, frame)); last_hist, last_ts = h, ts
                else:
                    d = cv2.compareHist(last_hist, h, cv2.HISTCMP_BHATTACHARYYA)
                    take, forced = False, False
                    if d > threshold:
                        take = True
                    elif (ts - last_ts) >= max_gap and d >= dedupe:
                        take, forced = True, True
                    if take:
                        if any(cv2.compareHist(k[1], h, cv2.HISTCMP_BHATTACHARYYA) < dedupe for k in kept):
                            dropped_dupes += 1
                        else:
                            kept.append((ts, h, frame)); last_hist, last_ts = h, ts
                            scene_hits += 0 if forced else 1
                            forced_hits += 1 if forced else 0
        idx += 1
    cap.release()

    n_candidates = len(kept)
    if len(kept) > max_count:
        pick = sorted({int(round(i * (len(kept) - 1) / (max_count - 1))) for i in range(max_count)})
        kept = [kept[i] for i in pick]
    saved: list[tuple[float, str]] = []
    for ts, _h, frame in kept:
        name = f"frame_{int(ts * 1000):08d}.jpg"
        cv2.imwrite(str(out_dir / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        saved.append((ts, name))
    stats = {"keyframe_threshold": threshold, "scene_change_keyframes": scene_hits, "forced_interval_keyframes": forced_hits,
             "dropped_near_duplicates": dropped_dupes, "candidates_before_cap": n_candidates,
             "keyframes_saved": len(saved), "keyframe_cap": max_count, "duration_s": round(duration, 2), "fps": round(fps, 2)}
    return saved, stats


def extract_video(file_path: str, source_id: UUID, storage: Path, whisper_model: str, threshold: float,
                  max_gap: float, max_count: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"warnings": []}
    units: list[dict[str, Any]] = []
    seq = 0

    kf_dir = storage / "keyframes" / str(source_id)
    kfs, kstats = detect_keyframes(file_path, kf_dir, threshold=threshold, max_gap=max_gap, max_count=max_count)
    meta.update(kstats)
    duration = kstats["duration_s"]

    if has_audio_stream(file_path):
        wav = storage / "tmp" / f"{source_id}.wav"
        try:
            extract_audio(file_path, str(wav))
            segs, asr_meta = transcribe(str(wav), whisper_model)
        finally:
            wav.unlink(missing_ok=True)
        meta.update(asr_meta)
        meta["asr_segments"] = len(segs)
        if not segs:
            meta["warnings"].append("ASR produced no speech segments")
        for g in group_segments(segs):
            units.append({"source_id": source_id, "source_type": "video", "unit_type": "caption", "content": g["text"],
                          "time_start": g["start"], "time_end": g["end"], "sequence_index": seq,
                          "unit_metadata": {"asr_engine": asr_meta["asr_engine"]}})
            seq += 1
    else:
        meta["warnings"].append("video has no audio stream; only on-screen content is indexed")

    for i, (ts, name) in enumerate(kfs):
        nxt = kfs[i + 1][0] if i + 1 < len(kfs) else max(duration, ts)
        units.append({"source_id": source_id, "source_type": "video", "unit_type": "keyframe",
                      "content": f"[Keyframe at {fmt_ts(ts)}]", "time_start": ts, "time_end": max(nxt, ts),
                      "image_path": f"keyframes/{source_id}/{name}", "sequence_index": seq,
                      "unit_metadata": {"timestamp": ts}})
        seq += 1
    return units, meta
