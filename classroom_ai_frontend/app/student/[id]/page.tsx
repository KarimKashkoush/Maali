"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getStudent } from "@/Api/getStudent";
import { getClassrooms } from "@/Api/getClassrooms";
import { errorMessage } from "@/Api/client";
import { attendanceLabels, type Classroom, type Student } from "@/Api/types";
import StudentImagesForm from "./StudentImagesForm";
import StudentEditor from "../../_components/students/StudentEditor";
import { ErrorNotice } from "../../_components/ApiStatus";
export default function StudentPage() {
  const id = Number(useParams().id);
  const [student, setStudent] = useState<Student | null>(null);
  const [classes, setClasses] = useState<Classroom[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { const [person, rooms] = await Promise.all([getStudent(id), getClassrooms()]); setStudent(person); setClasses(rooms); }, [id]);
  useEffect(() => { Promise.resolve().then(load).catch((e) => setError(errorMessage(e))).finally(() => setLoading(false)); }, [load]);
  if (loading) return <p className="py-20 text-center">جاري تحميل الطالب...</p>;
  if (!student) return <ErrorNotice message={error ?? "الطالب غير موجود."} />;
  return <div className="pb-12">
    <header className="mb-6 rounded-2xl bg-[#0F4C3A] p-6 text-white"><h1 className="text-3xl font-bold">{student.full_name}</h1><p className="mt-3">{student.classrooms?.classroom_name ?? classes.find((room) => room.id === student.class_id)?.classroom_name}</p><Link href={`/classroom/${student.class_id}`} className="mt-3 inline-block text-sm underline">فتح سبورة الفصل</Link></header>
    <ErrorNotice message={error} /><StudentEditor key={student.id + ":" + student.class_id} student={student} classrooms={classes} onSaved={load} />
    <StudentImagesForm studentId={student.id} studentImages={student.students_images ?? []} onSaved={load} />
    <section className="mt-8 rounded-2xl border bg-white p-6"><h2 className="mb-4 text-xl font-bold">سجلات الحضور</h2>{student.attendance_records?.length ? <ul className="divide-y">{student.attendance_records.map((record, index) => <li key={`${record.attendance_date}-${index}`} className="flex flex-wrap justify-between gap-3 py-3 text-sm"><span>{record.attendance_date ?? "—"}</span><span>{attendanceLabels[record.status]}{record.status === "late" ? ` · ${record.late_minutes} دقيقة تأخير` : ""}</span></li>)}</ul> : <p className="text-sm text-gray-500">لا توجد سجلات حضور بعد.</p>}</section>
  </div>;
}
