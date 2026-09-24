"use client";
import { useEffect, useState } from "react";
import { getSchools } from "@/Api/getSchools";
import { schoolTypeLabels, curriculumLabels, type School } from "@/Api/types";
import { errorMessage } from "@/Api/client";
import { EmptyState, ErrorNotice } from "../ApiStatus";
import ClassroomCard from "./ClassroomCard";
import GeneralInformation from "./GeneralInformation";
export default function Classrooms({ boardSetup = false, onClassroomSelect }: { boardSetup?: boolean; onClassroomSelect?: (id: number) => void }) {
  const [schools, setSchools] = useState<School[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [stageId, setStageId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getSchools().then((data) => { if (active) { setSchools(data); setSelectedId(data[0]?.id ?? null); } })
      .catch((e) => { if (active) setError(errorMessage(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  if (loading) return <p className="p-10 text-center">جاري تحميل المدارس...</p>;
  if (error) return <ErrorNotice message={error} />;
  if (!schools.length) return <EmptyState text="لم تضف مدارس بعد." />;
  const selected = schools.find((school) => school.id === selectedId) ?? schools[0];
  const stages = selected.stage ?? [];
  const selectedStage = stages.find((stage) => stage.id === stageId) ?? stages[0];
  const classes = selectedStage?.classrooms ?? [];
  const totals = schools.reduce((result, school) => {
    const stats = school.school_statistics;
    result.totalStudents += stats?.total_students ?? 0;
    result.totalPresent += stats?.total_present ?? 0;
    result.totalAbsent += stats?.total_absent ?? 0;
    result.totalClasses += stats?.total_classes ?? 0;
    result.activeClasses += stats?.active_classes ?? 0;
    return result;
  }, { totalStudents: 0, totalPresent: 0, totalAbsent: 0, totalClasses: 0, activeClasses: 0 });
  return <div>
    <GeneralInformation information={{ name: "المدارس", summary: { ...totals, attendanceRate: totals.totalStudents ? Math.round(totals.totalPresent / totals.totalStudents * 100) : 0 } }} showClasses />
    <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{schools.map((school) => <button key={school.id} onClick={() => { setSelectedId(school.id); setStageId(null); }} className={`rounded-2xl border-2 p-5 text-right ${selected.id === school.id ? "border-[#0F4C3A] bg-[#0F4C3A] text-white" : "border-transparent bg-white text-[#0F4C3A]"}`}>
      <h2 className="text-xl font-bold">{school.name ?? school.school_name}</h2><p className="mt-1 text-sm">{school.school_type ? schoolTypeLabels[school.school_type] : "نوع المدرسة غير محدد"} · {school.curriculum ? curriculumLabels[school.curriculum] : "المنهج غير محدد"}</p><p className="mt-2 text-sm">{school.school_statistics?.total_students ?? 0} طالب · {school.school_statistics?.total_classes ?? 0} فصل</p>
    </button>)}</div>
    <section className="mb-6 rounded-2xl border bg-white p-5"><h2 className="mb-3 text-lg font-bold">مراحل {selected.name}</h2><div className="flex flex-wrap gap-3">{stages.map((stage) => <button type="button" key={stage.id} aria-pressed={selectedStage?.id === stage.id} onClick={() => setStageId(stage.id)} className={selectedStage?.id === stage.id ? "rounded-xl bg-[#0F4C3A] px-4 py-3 text-white" : "rounded-xl border px-4 py-3 text-[#0F4C3A]"}>{stage.name ?? stage.stage_name} · {stage.classrooms?.length ?? 0} فصل</button>)}</div>{!stages.length && <p className="text-gray-500">لم تضف مراحل لهذه المدرسة بعد.</p>}</section>
    {selectedStage && <h3 className="mb-4 text-xl font-bold">فصول {selectedStage.name ?? selectedStage.stage_name}</h3>}
    {classes.length ? <section className="grid-auto-fit">{classes.map((classroom) => {
      const stats = classroom.classroom_statistics_classroom_id_fkey;
      return <ClassroomCard key={classroom.id} classroom={{ id: classroom.id, name: classroom.classroom_name, summary: { totalStudents: stats?.total_students ?? 0, totalPresent: stats?.total_present ?? 0, totalAbsent: stats?.total_absent ?? 0, attendanceRate: stats?.attendance_rate ?? 0 } }} selectForBoard={boardSetup} onSelect={onClassroomSelect} />;
    })}</section> : <EmptyState text={selectedStage ? "لا توجد فصول بهذه المرحلة." : "أضف مرحلة للمدرسة ثم أضف فصولها."} />}
  </div>;
}
