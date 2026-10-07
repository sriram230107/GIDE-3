import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def load_testset(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "_README" in data:
        raise SystemExit("Refusing to evaluate on the template. Copy it to testset.json and fill it with real questions.")
    items = data["items"]
    for it in items:
        assert it["bucket"] in ("answerable", "ambiguous", "off_material"), it
    return items


def save_run(kind: str, config: dict, metrics: dict, notes: str = "") -> Path:
    """Every run is written to evaluation/results/ (config + date + metrics). Nothing is overwritten or cherry-picked."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = RESULTS / f"{ts}_{kind}.json"
    p.write_text(json.dumps({"kind": kind, "date": ts, "config": config, "metrics": metrics, "notes": notes}, indent=2, default=str))
    return p


async def save_run_db(kind: str, config: dict, metrics: dict, notes: str = ""):
    from app.core.database import AsyncSessionLocal, init_db
    from app.database.models import EvalRun
    await init_db()
    async with AsyncSessionLocal() as s:
        s.add(EvalRun(kind=kind, config=config, metrics=metrics, notes=notes))
        await s.commit()
