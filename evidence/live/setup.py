"""Final sweep: register a live user, build knowledge, then run the live checks."""
import json
import urllib.request

BASE = "http://127.0.0.1:8123"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


if __name__ == "__main__":
    import urllib.error
    st, reg = call("POST", "/api/auth/register", {"email": "live@gide.local", "password": "livepass12345"})
    print("register:", st, str(reg)[:120])
    if st != 200:
        st, reg = call("POST", "/api/auth/login", {"email": "live@gide.local", "password": "livepass12345"})
        print("login:", st, str(reg)[:120])
    tok = reg["token"]
    st, courses = call("GET", "/api/courses", token=tok)
    print("courses:", st, str(courses)[:300])
    open("evidence/live/token.txt", "w").write(tok)
