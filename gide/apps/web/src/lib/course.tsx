"use client";
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, post } from "./api";
import type { Course } from "./types";

interface Ctx { courses: Course[]; course: Course | null; setCourseId: (id: string) => void; reload: () => Promise<void>; create: (t: string) => Promise<void> }
const C = createContext<Ctx>({ courses: [], course: null, setCourseId: () => {}, reload: async () => {}, create: async () => {} });
export const useCourse = () => useContext(C);

export function CourseProvider({ children }: { children: React.ReactNode }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [id, setId] = useState<string | null>(null);
  const reload = useCallback(async () => {
    if (!getToken()) return;
    try {
      const list = await api<Course[]>("/api/courses");
      setCourses(list);
      const saved = localStorage.getItem("gide_course");
      setId((cur) => cur && list.some((c) => c.id === cur) ? cur : list.find((c) => c.id === saved)?.id ?? list[0]?.id ?? null);
    } catch {}
  }, []);
  useEffect(() => { reload(); }, [reload]);
  const setCourseId = (x: string) => { setId(x); localStorage.setItem("gide_course", x); };
  const create = async (title: string) => { const c = await post<Course>("/api/courses", { title }); await reload(); setCourseId(c.id); };
  return <C.Provider value={{ courses, course: courses.find((c) => c.id === id) ?? null, setCourseId, reload, create }}>{children}</C.Provider>;
}
