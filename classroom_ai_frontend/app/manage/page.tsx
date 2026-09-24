"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, errorMessage, jsonBody } from "@/Api/client";
import { getSchools } from "@/Api/getSchools";
import { getClassrooms } from "@/Api/getClassrooms";
import { schoolTypeLabels, curriculumLabels, type Classroom, type School } from "@/Api/types";
import { buttonClass, ErrorNotice, Field, inputClass } from "../_components/ApiStatus";

const weekdays = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
export default function ManagePage() {
  const [schools, setSchools] = useState<School[]>([]);
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [schoolEdit, setSchoolEdit] = useState("");
  const [stageEdit, setStageEdit] = useState("");
  const [classEdit, setClassEdit] = useState("");
  const [classSchool, setClassSchool] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [schoolData, classData] = await Promise.all([getSchools(), getClassrooms()]);
    setSchools(schoolData); setClassrooms(classData);
  }, []);
  useEffect(() => { Promise.resolve().then(load).catch((e) => setError(errorMessage(e))).finally(() => setLoading(false)); }, [load]);
  const stages = schools.flatMap((school) => (school.stage ?? []).map((stage) => ({ ...stage, school_id: school.id })));
  const selectedSchool = schools.find((school) => String(school.id) === schoolEdit);
  const selectedStage = stages.find((stage) => String(stage.id) === stageEdit);
  const selectedClass = classrooms.find((classroom) => String(classroom.id) === classEdit);
  async function save(event: FormEvent<HTMLFormElement>, entity: "schools" | "stages" | "classrooms", id: string) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    setBusy(true); setError(null); setMessage(null);
    let values: Record<string, unknown>;
    if (entity === "schools") values = { name: String(data.get("name")).trim(), timezone: data.get("timezone"), school_type: data.get("school_type"), curriculum: data.get("curriculum") };
    else if (entity === "stages") values = { name: String(data.get("name")).trim(), ...(!id ? { school_id: Number(data.get("school_id")) } : {}) };
    else {
      values = { school_id: Number(data.get("school_id")), stage_id: data.get("stage_id") ? Number(data.get("stage_id")) : null, classroom_name: String(data.get("classroom_name")).trim(), attendance_start: data.get("attendance_start"), attendance_end: data.get("attendance_end"), grace_minutes: Number(data.get("grace_minutes")), absence_after_minutes: Number(data.get("absence_after_minutes")), weekdays: data.getAll("weekdays").map(Number), ...(id ? { schedule_effective: data.get("schedule_effective") } : {}) };
      if (!(values.weekdays as number[]).length) { setError("اختر يوم دراسة واحدًا على الأقل."); setBusy(false); return; }
      if (Number(values.absence_after_minutes) < Number(values.grace_minutes)) { setError("مهلة الغياب يجب ألا تقل عن مهلة التأخير."); setBusy(false); return; }
      if (String(values.attendance_end) <= String(values.attendance_start)) { setError("نهاية الدوام يجب أن تكون بعد موعد الحضور."); setBusy(false); return; }
    }
    try {
      await apiFetch(`/${entity}${id ? `/${id}` : ""}`, { method: id ? "PATCH" : "POST", ...jsonBody(values) });
      await load(); setMessage("تم حفظ البيانات بنجاح."); if (!id) form.reset();
    } catch (requestError) { setError(errorMessage(requestError)); }
    finally { setBusy(false); }
  }
  if (loading) return <p className="py-20 text-center">جاري تحميل الإدارة...</p>;
  return <div className="pb-12">
    <header className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-3xl font-bold text-[#0F4C3A]">إدارة المدارس والفصول</h1><p className="mt-2 text-sm text-gray-500">أضف المدرسة والمرحلة والفصل، ثم اربط الطلاب بالفصل.</p></div><Link href="/student/new" className={buttonClass}>إضافة طالب</Link></header>
    <ErrorNotice message={error} />{message && <p role="status" className="mb-4 rounded-xl bg-green-50 p-4 text-green-800">{message}</p>}
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border bg-white p-6"><h2 className="mb-4 text-xl font-bold">المدارس</h2>
        <Field label="إنشاء أو تعديل"><select value={schoolEdit} onChange={(event) => setSchoolEdit(event.target.value)} className={inputClass}><option value="">مدرسة جديدة</option>{schools.map((school) => <option key={school.id} value={school.id}>{school.name ?? school.school_name}</option>)}</select></Field>
        <form key={schoolEdit} onSubmit={(e) => save(e, "schools", schoolEdit)} className="mt-5 space-y-4">
          <Field label="اسم المدرسة"><input name="name" required maxLength={150} defaultValue={selectedSchool?.name ?? selectedSchool?.school_name ?? ""} className={inputClass} /></Field>
          <Field label="نوع المدرسة"><select name="school_type" required defaultValue={selectedSchool?.school_type ?? ""} className={inputClass}><option value="">اختر النوع</option>{Object.entries(schoolTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label="المنهج"><select name="curriculum" required defaultValue={selectedSchool?.curriculum ?? ""} className={inputClass}><option value="">اختر المنهج</option>{Object.entries(curriculumLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label="المنطقة الزمنية"><select name="timezone" defaultValue={selectedSchool?.timezone ?? "Asia/Riyadh"} className={inputClass}><option value="Asia/Riyadh">السعودية — الرياض</option><option value="Africa/Cairo">مصر — القاهرة</option><option value="Asia/Dubai">الإمارات — دبي</option><option value="Asia/Kuwait">الكويت</option><option value="Asia/Qatar">قطر</option><option value="UTC">UTC</option>{selectedSchool?.timezone && !["Asia/Riyadh", "Africa/Cairo", "Asia/Dubai", "Asia/Kuwait", "Asia/Qatar", "UTC"].includes(selectedSchool.timezone) && <option value={selectedSchool.timezone}>{selectedSchool.timezone}</option>}</select></Field>
          <button disabled={busy} className={buttonClass}>{schoolEdit ? "حفظ المدرسة" : "إضافة المدرسة"}</button>
        </form>
      </section>
      <section className="rounded-2xl border bg-white p-6"><h2 className="mb-4 text-xl font-bold">المراحل الدراسية</h2>
        <Field label="إنشاء أو تعديل"><select value={stageEdit} onChange={(event) => setStageEdit(event.target.value)} className={inputClass}><option value="">مرحلة جديدة</option>{stages.map((stage) => <option key={stage.id} value={stage.id}>{schools.find((school) => school.id === stage.school_id)?.name} — {stage.name ?? stage.stage_name}</option>)}</select></Field>
        <form key={stageEdit} onSubmit={(e) => save(e, "stages", stageEdit)} className="mt-5 space-y-4">
          <Field label="المدرسة"><select name="school_id" required disabled={!!stageEdit} defaultValue={selectedStage?.school_id ?? ""} className={inputClass}><option value="">اختر المدرسة</option>{schools.map((school) => <option key={school.id} value={school.id}>{school.name ?? school.school_name}</option>)}</select></Field>
          <Field label="اسم المرحلة"><input name="name" required maxLength={150} defaultValue={selectedStage?.name ?? selectedStage?.stage_name ?? ""} className={inputClass} /></Field>
          <button disabled={busy || !schools.length} className={buttonClass}>{stageEdit ? "حفظ المرحلة" : "إضافة المرحلة"}</button>
        </form>
      </section>
      <section className="rounded-2xl border bg-white p-6 lg:col-span-2"><h2 className="mb-4 text-xl font-bold">الفصول ومواعيد الحضور</h2>
        <Field label="إنشاء أو تعديل"><select value={classEdit} onChange={(event) => { setClassEdit(event.target.value); setClassSchool(String(classrooms.find((classroom) => String(classroom.id) === event.target.value)?.school_id ?? "")); }} className={inputClass}><option value="">فصل جديد</option>{classrooms.map((classroom) => <option key={classroom.id} value={classroom.id}>{schools.find((school) => school.id === classroom.school_id)?.name} — {stages.find((stage) => stage.id === classroom.stage_id)?.name} — {classroom.classroom_name}</option>)}</select></Field>
        <form key={classEdit} onSubmit={(e) => save(e, "classrooms", classEdit)} className="mt-5 space-y-5">
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="المدرسة"><select name="school_id" value={classSchool} onChange={(event) => setClassSchool(event.target.value)} required className={inputClass}><option value="">اختر المدرسة</option>{schools.map((school) => <option key={school.id} value={school.id}>{school.name ?? school.school_name}</option>)}</select></Field>
            <Field label="المرحلة"><select key={classSchool} name="stage_id" required defaultValue={String(selectedClass?.school_id) === classSchool ? selectedClass?.stage_id ?? "" : ""} className={inputClass}><option value="">اختر المرحلة</option>{stages.filter((stage) => String(stage.school_id) === classSchool).map((stage) => <option key={stage.id} value={stage.id}>{stage.name ?? stage.stage_name}</option>)}</select></Field>
            <Field label="اسم الفصل"><input name="classroom_name" required maxLength={150} defaultValue={selectedClass?.classroom_name ?? ""} className={inputClass} /></Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="موعد الحضور"><input name="attendance_start" type="time" required defaultValue={selectedClass?.attendance_start?.slice(0, 5) ?? "07:00"} className={inputClass} /></Field>
            <Field label="مهلة التأخير (دقائق)"><input name="grace_minutes" type="number" required min="0" max="360" defaultValue={selectedClass?.grace_minutes ?? 10} className={inputClass} /></Field>
            <Field label="مهلة الغياب من موعد الحضور (دقائق)"><input name="absence_after_minutes" type="number" required min="0" max="720" defaultValue={selectedClass?.absence_after_minutes ?? 30} className={inputClass} /></Field>
            <Field label="نهاية الدوام"><input name="attendance_end" type="time" required defaultValue={selectedClass?.attendance_end?.slice(0, 5) ?? "14:00"} className={inputClass} /></Field>
          </div>
          <fieldset><legend className="mb-3 text-sm font-semibold">أيام الدراسة</legend><div className="flex flex-wrap gap-4">{weekdays.map((day, index) => <label key={day} className="flex items-center gap-2 text-sm"><input type="checkbox" name="weekdays" value={index} defaultChecked={(selectedClass?.weekdays ?? [0, 1, 2, 3, 4]).includes(index)} />{day}</label>)}</div></fieldset>
          {classEdit && <fieldset className="rounded-xl border bg-amber-50 p-4"><legend className="font-semibold">تطبيق تعديل المواعيد</legend><label className="ml-6 inline-flex gap-2"><input type="radio" name="schedule_effective" value="tomorrow" defaultChecked />من بكرة</label><label className="inline-flex gap-2"><input type="radio" name="schedule_effective" value="today" />تطبيق على اليوم</label><p className="mt-3 text-sm">التطبيق على اليوم يعيد حساب التأخير والغياب التلقائي بمواعيدك الجديدة، مع حفظ أوقات الوصول والغياب اليدوي. عند إلغاء دوام اليوم تصبح حالته إجازة. تبقى الأيام السابقة كما هي، وتُستبدل المواعيد المؤجلة سابقًا بالمواعيد الجديدة.</p></fieldset>}
          <p className="text-sm text-gray-500">كل المواعيد بتوقيت المدرسة. الغياب يُحتسب بعد انتهاء مهلته، والتأخير يُحسب على الخادم عند وصول الطالب. اختر سريان مواعيد الفصل عند التعديل؛ الافتراضي من بكرة. تغيير المنطقة الزمنية من إعدادات المدرسة يبدأ من اليوم التالي.</p>
          <button disabled={busy || !schools.length} className={buttonClass}>{busy ? "جاري الحفظ..." : classEdit ? "حفظ الفصل" : "إضافة الفصل"}</button>
        </form>
      </section>
    </div>
  </div>;
}
