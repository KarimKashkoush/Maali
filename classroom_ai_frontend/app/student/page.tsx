"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getStudents } from "@/Api/getStudents";
import { getClassrooms } from "@/Api/getClassrooms";
import { errorMessage } from "@/Api/client";
import type { Classroom, Student } from "@/Api/types";
import { buttonClass, EmptyState, ErrorNotice, inputClass } from "../_components/ApiStatus";
export default function StudentsPage() {
  const [students, setStudents] = useState<Student[]>([]);
  const [classes, setClasses] = useState<Classroom[]>([]);
  const [classId, setClassId] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Promise.all([getStudents(), getClassrooms()]).then(([people, rooms]) => { setStudents(people); setClasses(rooms); }).catch((e) => setError(errorMessage(e))).finally(() => setLoading(false)); }, []);
  const shown = students.filter((student) => (!classId || String(student.class_id) === classId) && student.full_name.includes(query));
  return <div className="pb-12">
    <header className="mb-6 flex flex-wrap items-center justify-between gap-3"><h1 className="text-3xl font-bold text-[#0F4C3A]">الطلاب</h1><Link href="/student/new" className={buttonClass}>إضافة طالب</Link></header>
    <div className="mb-5 flex flex-wrap gap-4"><input aria-label="بحث باسم الطالب" placeholder="ابحث باسم الطالب" value={query} onChange={(e) => setQuery(e.target.value)} className={inputClass + " max-w-sm"} /><select aria-label="الفصل" value={classId} onChange={(e) => setClassId(e.target.value)} className={inputClass + " max-w-sm"}><option value="">كل الفصول</option>{classes.map((room) => <option key={room.id} value={room.id}>{room.classroom_name}</option>)}</select></div>
    <ErrorNotice message={error} />
    {loading ? <p className="p-10 text-center">جاري تحميل الطلاب...</p> : !shown.length ? <EmptyState text="لا يوجد طلاب مطابقون." /> : <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{shown.map((student) => <Link href={`/student/${student.id}`} key={student.id} className="rounded-2xl border bg-white p-5 transition hover:border-[#0F4C3A]"><h2 className="text-lg font-bold">{student.full_name}</h2><p className="mt-2 text-sm text-gray-500">{classes.find((room) => room.id === student.class_id)?.classroom_name ?? "غير مرتبط بفصل"}</p><p className="mt-3 text-sm text-[#0F4C3A]">{student.is_active === false ? "غير نشط" : "تعديل البيانات والصور ←"}</p></Link>)}</div>}
  </div>;
}
