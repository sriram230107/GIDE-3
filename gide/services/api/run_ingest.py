import asyncio
import httpx
from pathlib import Path
import time
import json

base_url = "http://127.0.0.1:8000"

async def main():
    async with httpx.AsyncClient(base_url=base_url, timeout=300.0) as client:
        # Register
        email = f"test_{int(time.time())}@example.com"
        pw = "test1234"
        print(f"Registering {email}")
        res = await client.post("/api/auth/register", json={"email": email, "password": pw})
        print(res.status_code, res.text)
        
        token = res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.headers.update(headers)
        client.headers.update(headers)
        
        # Create course
        res = await client.post("/api/courses", json={"title": "Attention Paper", "description": "Transformers"})
        print("Course created:", res.status_code, res.text)
        course_id = res.json()["id"]
        
        # Upload PDF
        file_path = Path(r"D:\GIDE-3\evidence\step3\source_files\attention.pdf")
        with open(file_path, "rb") as f:
            res = await client.post(f"/api/sources/upload", data={"course_id": course_id}, files={"file": ("attention.pdf", f, "application/pdf")})
        print("Source uploaded:", res.status_code, res.text)
        source_id = res.json()["id"]
        
        # Poll for completion
        while True:
            res = await client.get(f"/api/sources/{source_id}")
            status = res.json()["status"]
            print(f"Source status: {status}")
            if status in ("completed", "failed"):
                break
            await asyncio.sleep(5)
            
        if status != "completed":
            print("Failed to ingest PDF")
            return
            
        # Build knowledge
        res = await client.post(f"/api/courses/{course_id}/build-knowledge")
        print("Build knowledge:", res.status_code, res.text)
        
        # Wait for build
        while True:
            res = await client.get(f"/api/courses/{course_id}/knowledge-status")
            ready = res.json().get("ready", False)
            print(f"Knowledge status:", res.json())
            if ready:
                break
            await asyncio.sleep(5)
            
        with open("../../evidence/step3/ingest.log", "w") as f:
            f.write(f"Course ID: {course_id}\n")
            f.write(f"Token: {token}\n")
            f.write(f"Final stats: {json.dumps(res.json(), indent=2)}\n")

if __name__ == "__main__":
    asyncio.run(main())
