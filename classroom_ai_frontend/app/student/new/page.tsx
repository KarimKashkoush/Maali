"use client";
import { useEffect, useState } from "react";
import { getClassrooms } from "@/Api/getClassrooms";
import { errorMessage } from "@/Api/client";
import type { Classroom } from "@/Api/types";
import StudentEditor from "../../_components/students/StudentEditor";
import { EmptyState, ErrorNotice } from "../../_components/ApiStatus";
export default function NewStudentPage() {
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getClassrooms().then(setClassrooms).catch((e) => setError(errorMessage(e))).finally(() => setLoading(false)); }, []);
  return <div className="mx-auto max-w-2xl pb-12"><h1 className="mb-6 text-3xl font-bold text-[#0F4C3A]">إضافة طالب للفصل</h1><ErrorNotice message={error} />{loading ? <p>جاري تحميل الفصول...</p> : classrooms.length ? <StudentEditor classrooms={classrooms} /> : !error && <EmptyState text="أضف مدرسة ومرحلة وفصلًا أولًا." />}</div>;
}
