"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { post, setToken } from "@/lib/api";
import { Btn, ErrorBox } from "@/components/Shell";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await post(`/api/auth/${mode}`, { email, password });
      setToken(r.token); router.replace("/");
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-8">
        <h1 className="text-2xl font-semibold text-zinc-100">Gide<span className="text-emerald-400">.</span></h1>
        <p className="text-sm text-zinc-400">{mode === "login" ? "Sign in to continue learning." : "Create your account."}</p>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="w-full rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100" />
        <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password (min 8 chars)" className="w-full rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100" />
        <ErrorBox msg={err} />
        <Btn disabled={busy} className="w-full">{busy ? "…" : mode === "login" ? "Sign in" : "Register"}</Btn>
        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")} className="w-full text-xs text-zinc-500 hover:text-zinc-300">
          {mode === "login" ? "No account? Register" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
