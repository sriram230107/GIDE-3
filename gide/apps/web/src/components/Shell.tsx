"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/api";
import { CourseProvider, useCourse } from "@/lib/course";

const NAV = [["/", "Dashboard"], ["/sources", "Sources"], ["/tutor", "Tutor"], ["/assessments", "Assessments"], ["/map", "Knowledge map"]];

function Inner({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { courses, course, setCourseId, create } = useCourse();
  const [title, setTitle] = useState("");
  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900/40 p-4 md:flex">
        <div className="mb-6 text-xl font-semibold tracking-tight">Gide<span className="text-emerald-400">.</span></div>
        <nav className="flex flex-col gap-1">
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} className={`rounded-lg px-3 py-2 text-sm transition ${path === href ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"}`}>{label}</Link>
          ))}
        </nav>
        <div className="mt-auto space-y-2 text-xs">
          <div className="text-zinc-500">Course</div>
          {courses.length > 0 && (
            <select value={course?.id ?? ""} onChange={(e) => setCourseId(e.target.value)} className="w-full rounded-lg border border-zinc-800 bg-zinc-900 p-2">
              {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          )}
          <form onSubmit={async (e) => { e.preventDefault(); if (title.trim()) { await create(title.trim()); setTitle(""); } }} className="flex gap-1">
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New course" className="min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 p-2" />
            <button className="rounded-lg bg-zinc-800 px-2 hover:bg-zinc-700">+</button>
          </form>
          <button onClick={() => { setToken(null); location.href = "/login"; }} className="text-zinc-500 hover:text-zinc-300">Sign out</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (path !== "/login" && !getToken()) router.replace("/login");
    else setReady(true);
  }, [path, router]);
  if (path === "/login") return <>{children}</>;
  if (!ready) return null;
  return <CourseProvider><Inner>{children}</Inner></CourseProvider>;
}

export function NeedCourse({ children }: { children: (courseId: string) => React.ReactNode }) {
  const { course } = useCourse();
  if (!course) return <p className="text-sm text-zinc-400">Create or select a course in the sidebar to begin.</p>;
  return <>{children(course.id)}</>;
}

export const Card = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div className={`rounded-2xl border border-zinc-800 bg-zinc-900/50 p-5 ${className}`}>{children}</div>
);
export const Btn = (p: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "ghost" }) => (
  <button {...p} className={`rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-40 ${p.tone === "ghost" ? "border border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "bg-emerald-500 text-zinc-950 hover:bg-emerald-400"} ${p.className ?? ""}`} />
);
export const ErrorBox = ({ msg }: { msg: string | null }) => msg ? <div className="rounded-lg border border-red-900 bg-red-950/50 p-3 text-sm text-red-300">{msg}</div> : null;
