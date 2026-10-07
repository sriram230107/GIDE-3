import cv2
import numpy as np
from app.ingestion.video_parser import detect_keyframes, group_segments, fmt_ts


def _video(path, colors, frames_each=100, fps=5):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
    for c in colors:
        for _ in range(frames_each):
            w.write(np.full((240, 320, 3), c, np.uint8))
    w.release()


def test_scene_changes_found_at_right_timestamps(tmp_path):
    v = tmp_path / "v.mp4"
    _video(v, [(200, 30, 30), (30, 200, 30), (30, 30, 200)])
    kfs, st = detect_keyframes(str(v), tmp_path / "kf")
    assert [round(t) for t, _ in kfs] == [0, 20, 40]
    assert st["scene_change_keyframes"] == 2


def test_static_video_does_not_spam_forced_keyframes(tmp_path):
    v = tmp_path / "s.mp4"
    _video(v, [(90, 90, 90)], frames_each=350)
    kfs, st = detect_keyframes(str(v), tmp_path / "kf")
    assert len(kfs) == 1 and st["forced_interval_keyframes"] == 0


def test_cap_limits_keyframes(tmp_path):
    v = tmp_path / "m.mp4"
    _video(v, [(i * 20, 255 - i * 20, 40) for i in range(10)], frames_each=10)
    kfs, st = detect_keyframes(str(v), tmp_path / "kf", max_count=4)
    assert len(kfs) <= 4 and st["candidates_before_cap"] >= 5


def test_group_segments_and_fmt():
    g = group_segments([{"start": 0, "end": 5, "text": "a"}, {"start": 5.5, "end": 12, "text": "b"}, {"start": 40, "end": 45, "text": "c"}])
    assert len(g) == 2 and g[0]["text"] == "a b"
    assert fmt_ts(75) == "01:15" and fmt_ts(3725) == "1:02:05"
