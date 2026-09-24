"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, errorMessage, jsonBody } from "@/Api/client";
import type { Classroom, Student } from "@/Api/types";
import { buttonClass, ErrorNotice, Field, inputClass } from "../ApiStatus";
import StudentPhotoPicker from "./StudentPhotoPicker";
export default function StudentEditor({ classrooms, student, onSaved }: { classrooms: Classroom[]; student?: Student; onSaved?: () => Promise<void> }) {
  const router = useRouter();
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setMessage(null);
    const data = new FormData(event.currentTarget);
    try {
      let response: Response;
      if (student) response = await apiFetch(`/students/${student.id}`, { method: "PATCH", ...jsonBody({ full_name: String(data.get("full_name")).trim(), class_id: Number(data.get("class_id")), is_active: data.get("is_active") === "on" }) });
      else {
        if (photo) data.set("photo", photo);
        data.set("full_name", String(data.get("full_name")).trim());
        response = await apiFetch("/students", { method: "POST", body: data });
      }
      const saved = await response.json() as Student;
      if (student) { await onSaved?.(); setMessage("تم حفظ بيانات الطالب."); }
      else router.push(`/student/${saved.id}`);
    } catch (requestError) { setError(errorMessage(requestError)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-5 rounded-2xl border bg-white p-6">
    <h2 className="text-xl font-bold text-[#0F4C3A]">{student ? "بيانات الطالب والفصل" : "طالب جديد"}</h2>
    <ErrorNotice message={error} />{message && <p role="status" className="text-green-700">{message}</p>}
    <Field label="اسم الطالب كاملًا"><input name="full_name" required maxLength={150} defaultValue={student?.full_name ?? ""} className={inputClass} /></Field>
    <Field label="الفصل"><select name="class_id" required defaultValue={student?.class_id ?? ""} className={inputClass}><option value="">اختر الفصل</option>{classrooms.map((classroom) => <option key={classroom.id} value={classroom.id}>{classroom.classroom_name}</option>)}</select></Field>
    {!student && <StudentPhotoPicker file={photo} onChange={setPhoto} disabled={busy} />}
    {student && <label className="flex items-center gap-2 text-sm"><input name="is_active" type="checkbox" defaultChecked={student.is_active !== false} />طالب نشط</label>}
    <button disabled={busy || !classrooms.length} className={buttonClass}>{busy ? "جاري الحفظ..." : student ? "حفظ بيانات الطالب" : "إضافة الطالب"}</button>
  </form>;
}
