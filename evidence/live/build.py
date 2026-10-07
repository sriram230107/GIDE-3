"""Enqueue build-knowledge for the Attention Paper course; poll knowledge-status."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8123"
TOK = open("evidence/live/token.txt").read().strip()
CID = "88f8e4b5-b29c-45e1-bf9b-75198e2b4050"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOK}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


if __name__ == "__main__":
    import urllib.error
    st, r = call("POST", f"/api/courses/{CID}/build-knowledge")
    print("build:", st, str(r)[:200], flush=True)
    t0 = time.time()
    while time.time() - t0 < 1500:
        st, s = call("GET", f"/api/courses/{CID}/knowledge-status")
        print(f"t={time.time()-t0:.0f}s", s, flush=True)
        if isinstance(s, dict) and s.get("ready"):
            break
        time.sleep(30)
    print("elapsed:", round(time.time() - t0, 1))
