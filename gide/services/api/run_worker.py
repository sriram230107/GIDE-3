import sys
import time
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from arq.worker import run_worker
from app.worker import WorkerSettings

if __name__ == "__main__":
    while True:
        try:
            print("[Arq Runner] Starting Arq worker process...")
            run_worker(WorkerSettings)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Arq Runner] Worker loop exception: {e}. Restarting in 2s...")
            time.sleep(2)
