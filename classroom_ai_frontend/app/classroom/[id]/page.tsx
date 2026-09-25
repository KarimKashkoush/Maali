"use client";
import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Camera, RefreshCcw } from "lucide-react";
import { apiFetch, apiJson, errorMessage, jsonBody } from "@/Api/client";
import { attendanceLabels, type Classroom, type DailyAttendance, type DailyRecord, type Student } from "@/Api/types";
import { buttonClass, ErrorNotice } from "../../_components/ApiStatus";

const BOARD_KEY = "classroom-ai:board-classroom-id";
type Face = { top: number; right: number; bottom: number; left: number; matched: boolean; student_name: string | null; confidence: number; reason?: string | null };
type Frame = { frame_width: number; frame_height: number; detections: Face[]; processing_ms?: number };
type Session = { session_id: number; enrolled_students: number };
function time(value: string | null | undefined, timezone: string) { return value ? new Intl.DateTimeFormat("ar-SA", { hour: "2-digit", minute: "2-digit", timeZone: timezone }).format(new Date(value)) : "—"; }

export default function ClassroomPage() {
  const id = Number(useParams().id);
  return <AttendanceBoard key={id} id={id} />;
}
function AttendanceBoard({ id }: { id: number }) {
  const router = useRouter();
  const [classroom, setClassroom] = useState<Classroom | null>(null);
  const [daily, setDaily] = useState<DailyAttendance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "starting" | "running" | "stopping">("idle");
  const [frameSide, setFrameSide] = useState(1280);
  const overlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [latency, setLatency] = useState<{total: number; processing: number | null} | null>(null);
  const [enrolled, setEnrolled] = useState(0);
  const [faces, setFaces] = useState<Face[]>([]);
  const [size, setSize] = useState({ width: 16, height: 9 });
  const [manualBusy, setManualBusy] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null); const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null); const sessionRef = useRef<number | null>(null);
  const generationRef = useRef(0); const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!Number.isSafeInteger(id) || id <= 0) return;
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    window.localStorage.setItem(BOARD_KEY, String(id));
    async function poll() {
      try {
        const [data, roster] = await Promise.all([apiJson<DailyAttendance>(`/attendance/daily/class/${id}`, { signal: abort.signal }), apiJson<Classroom>(`/classrooms/${id}`, { signal: abort.signal })]);
        if (!abort.signal.aborted) { setDaily(data); setClassroom(roster); }
      }
      catch (e) { if (!abort.signal.aborted) setError(errorMessage(e)); }
      finally { if (!abort.signal.aborted) timer = setTimeout(poll, 5000); }
    }
    apiJson<Classroom>(`/classrooms/${id}`, { signal: abort.signal }).then(async (data) => { if (!abort.signal.aborted) setClassroom(data); await poll(); })
      .catch((e) => { if (!abort.signal.aborted) setError(errorMessage(e)); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => { abort.abort(); clearTimeout(timer); };
  }, [id]);
  useEffect(() => () => {
    if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
    generationRef.current++; if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort(); streamRef.current?.getTracks().forEach((track) => track.stop());
    if (sessionRef.current) void fetch(`/api/backend/attendance/live/stop/${sessionRef.current}`, { method: "POST", credentials: "same-origin", keepalive: true }).catch(() => {});
  }, []);
  function clearCamera() {
    if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
    generationRef.current++; if (timerRef.current) clearTimeout(timerRef.current); timerRef.current = null;
    abortRef.current?.abort(); abortRef.current = null; streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null; setFaces([]); setLatency(null);
  }
  async function refresh() { setDaily(await apiJson<DailyAttendance>(`/attendance/daily/class/${id}`)); }
  async function stop() {
    const session = sessionRef.current; sessionRef.current = null; clearCamera(); setState("stopping");
    try { if (session) await apiFetch(`/attendance/live/stop/${session}`, { method: "POST" }); await refresh(); }
    catch (e) { setError(errorMessage(e)); } finally { setState("idle"); }
  }
  async function capture(session: number, generation: number) {
    if (generation !== generationRef.current) return;
    const video = videoRef.current; const canvas = canvasRef.current; const sentAt = performance.now();
    try {
      if (video && canvas && video.videoWidth) {
        const scale = Math.min(1, frameSide / Math.max(video.videoWidth, video.videoHeight)); canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
        canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
        if (generation !== generationRef.current) return;
        if (blob) {
          const form = new FormData(); form.append("frame", blob, "camera.jpg"); const abort = new AbortController(); abortRef.current = abort;
          const result = await apiJson<Frame>(`/attendance/live/frame/${session}`, { method: "POST", body: form, signal: abort.signal });
          if (generation !== generationRef.current) return;
          setLatency({total: Math.round(performance.now() - sentAt), processing: result.processing_ms ?? null});
          setSize({ width: result.frame_width || canvas.width, height: result.frame_height || canvas.height }); if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
          // Do not draw old coordinates over a person who may already have moved.
          setFaces(performance.now() - sentAt <= 2000 ? result.detections ?? [] : []);
          overlayTimerRef.current = setTimeout(() => { if (generation === generationRef.current) setFaces([]); }, Math.max(0, Math.min(1000, 2000 - (performance.now() - sentAt))));
        }
      }
    } catch (e) { if (generation !== generationRef.current) return; setError(errorMessage(e)); await stop(); return; }
    // Schedule only after the response: frames can never overlap.
    if (generation === generationRef.current) timerRef.current = setTimeout(() => void capture(session, generation), 100);
  }
  async function start() {
    if (!classroom || state !== "idle") return;
    setError(null); setState("starting"); const generation = ++generationRef.current; let created: number | null = null;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("الكاميرا تحتاج متصفحًا يدعمها واتصال HTTPS أو localhost.");
      const result = await apiJson<Session>("/attendance/live/start", { method: "POST", ...jsonBody({ class_id: classroom.id, camera_mode: "browser" }) }); created = result.session_id;
      if (generation !== generationRef.current) { await apiFetch(`/attendance/live/stop/${created}`, { method: "POST" }); return; }
      sessionRef.current = created; setEnrolled(result.enrolled_students);
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      if (generation !== generationRef.current) { stream.getTracks().forEach((track) => track.stop()); return; }
      streamRef.current = stream; if (!videoRef.current) throw new Error("تعذر تجهيز نافذة الكاميرا.");
      videoRef.current.srcObject = stream; await videoRef.current.play(); if (generation !== generationRef.current) return;
      setSize({ width: videoRef.current.videoWidth || 16, height: videoRef.current.videoHeight || 9 }); setState("running"); void refresh().catch(e => { if (generation === generationRef.current) setError(errorMessage(e)); }); void capture(created, generation);
    } catch (e) {
      if (generation !== generationRef.current) return;
      clearCamera(); sessionRef.current = null; setState("idle"); setError(errorMessage(e));
      if (created) await apiFetch(`/attendance/live/stop/${created}`, { method: "POST" }).catch(() => {});
    }
  }
  async function manual(student: Student, present: boolean) {
    setManualBusy(student.id); setError(null);
    try {
      const updated = await apiJson<DailyRecord>(`/attendance/daily/class/${id}/students/${student.id}`, { method: "PATCH", ...jsonBody({ present }) });
      setDaily((previous) => previous ? { ...previous, records: previous.records.map((record) => record.student_id === student.id ? updated : record) } : previous);
    } catch (e) { setError(errorMessage(e)); } finally { setManualBusy(null); }
  }
  if (!Number.isSafeInteger(id) || id <= 0) return <ErrorNotice message="رقم الفصل غير صالح." />;
  if (loading) return <p className="py-20 text-center">جاري تحميل الفصل...</p>;
  if (!classroom) return <div><ErrorNotice message={error ?? "الفصل غير موجود."} /><Link href="/classrooms" className="underline">العودة إلى الفصول</Link></div>;
  const students = classroom.students ?? []; const records = daily?.records ?? []; const byId = new Map(records.map((record) => [record.student_id, record]));
  const timezone = daily?.timezone ?? "Asia/Riyadh";
  return <div className="pb-10">
    <header className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-gray-500">سبورة الفصل · {daily?.attendance_date}</p><h1 className="text-3xl font-bold text-[#0F4C3A]">{classroom.classroom_name}</h1></div><button onClick={() => { window.localStorage.removeItem(BOARD_KEY); router.push("/classrooms"); }} className="rounded-xl border px-4 py-2 text-sm font-semibold text-[#0F4C3A]"><RefreshCcw className="ml-2 inline h-4 w-4" />تغيير الفصل</button></header>
    <div className="mb-5 flex flex-wrap gap-3"><div className="rounded-2xl bg-white px-4 py-3">الإجمالي: <b>{students.length}</b></div>{(["present", "late", "absent", "pending"] as const).map((status) => <div key={status} className={`rounded-2xl px-4 py-3 ${status === "present" ? "bg-green-50 text-green-800" : status === "late" ? "bg-amber-50 text-amber-800" : status === "absent" ? "bg-red-50 text-red-800" : "bg-white"}`}>{attendanceLabels[status]}: <b>{records.filter((record) => record.status === status).length}</b></div>)}</div>
    {daily && <p className="mb-5 rounded-xl border bg-white p-4 text-sm text-gray-600">{daily.is_school_day ? `موعد الحضور ${daily.schedule.attendance_start.slice(0, 5)} · مهلة التأخير ${daily.schedule.grace_minutes} دقائق · تثبيت الغياب بعد ${daily.schedule.absence_after_minutes} دقيقة · نهاية الدوام ${daily.schedule.attendance_end.slice(0, 5)} (${timezone})` : "اليوم إجازة لهذا الفصل."}</p>}
    <label className="mb-3 flex flex-wrap items-center gap-2 text-sm">دقة بث التعرف<select value={frameSide} disabled={state !== "idle"} onChange={event => setFrameSide(Number(event.target.value))} className="rounded-lg border bg-white p-2"><option value={960}>سريع — للوجوه القريبة</option><option value={1280}>متوازن — HD</option><option value={1920}>تفاصيل أعلى — يحتاج معالجة أسرع</option></select><span className="text-gray-500">اختيار السرعة يقلل تفاصيل الوجوه البعيدة. غيّر الوضع قبل بدء التسجيل.</span></label>
    <ErrorNotice message={error} />
    {state === "running" && <p role="status" className="mb-3 text-sm text-gray-600">{latency ? `استجابة آخر لقطة: ${(latency.total / 1000).toFixed(1)} ثانية${latency.processing === null ? "" : ` · معالجة الصورة: ${(latency.processing / 1000).toFixed(1)} ثانية`}` : "جاري تحليل أول لقطة..."} · تُخفى المربعات إذا تجاوز عمر النتيجة ثانيتين.{latency && latency.total > 3000 ? " الاستجابة بطيئة؛ قد تتأخر المربعات عن حركة الوجه." : ""}</p>}
    <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="order-2 overflow-hidden rounded-3xl border bg-white xl:order-1"><div className="border-b p-4"><h2 className="font-bold text-[#0F4C3A]">طلاب الفصل</h2><p className="mt-1 text-xs text-gray-500">يمكن تعديل الحضور يدويًا عند الحاجة.</p><Link href="/student/new" className="mt-2 inline-block text-sm text-[#0F4C3A] underline">إضافة طالب</Link></div><div className="max-h-[68vh] divide-y overflow-y-auto">{!students.length && <p className="p-6 text-sm text-gray-500">لم يضف طلاب لهذا الفصل بعد.</p>}{students.map((student) => {
        const record = byId.get(student.id); const status = record?.status ?? "pending"; const checkedIn = status === "present" || status === "late";
        return <article key={student.id} className={`p-4 ${checkedIn ? "bg-green-50/60" : ""}`}><div className="flex items-center justify-between gap-2"><Link href={`/student/${student.id}`} className="font-semibold hover:underline">{student.full_name}</Link><span className={`rounded-full px-2 py-1 text-xs ${checkedIn ? "bg-green-100 text-green-800" : status === "absent" ? "bg-red-100 text-red-800" : "bg-gray-100 text-gray-700"}`}>{attendanceLabels[status]}</span></div><p className="mt-2 text-xs text-gray-500">{checkedIn ? `الوصول ${time(record?.check_in_at, timezone)}${status === "late" ? ` · تأخير ${record?.late_minutes ?? 0} دقيقة` : ""}` : status === "not_scheduled" ? "لا يوجد دوام اليوم" : "لم يسجل وصوله"}</p><button disabled={manualBusy !== null || !daily?.is_school_day} onClick={() => manual(student, !checkedIn)} className="mt-3 text-xs text-[#0F4C3A] underline disabled:opacity-40">{manualBusy === student.id ? "جاري الحفظ..." : checkedIn ? "تسجيل غياب يدوي" : "تسجيل حضور يدوي"}</button></article>;
      })}</div></aside>
      <section className="order-1 overflow-hidden rounded-3xl border bg-white xl:order-2"><div className="flex flex-wrap items-center justify-between gap-3 p-4"><div><h2 className="font-bold text-[#0F4C3A]">كاميرا الحضور</h2><p className="mt-1 text-sm text-gray-500">عدم ظهور طالب في لقطة لا يسجل غيابه. مؤشر التشابه ليس نسبة دقة أو احتمال صحة الهوية.</p>{state === "running" && <p className="mt-1 text-xs text-amber-700">التعرف متاح لـ {enrolled} من {students.length} طالب.</p>}</div>{state === "idle" ? <button disabled={!daily?.is_school_day || !students.length} onClick={start} className={buttonClass}><Camera className="ml-2 inline h-5 w-5" />بدء التسجيل</button> : <button disabled={state === "stopping"} onClick={stop} className="rounded-xl bg-red-600 px-5 py-3 font-bold text-white disabled:opacity-50">{state === "starting" ? "إلغاء تشغيل الكاميرا" : state === "stopping" ? "جاري الإيقاف..." : "إنهاء التسجيل"}</button>}</div>
        <div className="relative bg-black" style={{ aspectRatio: `${size.width}/${size.height}` }}><video ref={videoRef} muted playsInline className={state === "running" ? "h-full w-full object-contain" : "invisible h-full w-full"} /><canvas ref={canvasRef} hidden />{state === "running" ? <><span className="absolute right-4 top-4 rounded-full bg-red-600 px-3 py-1 text-xs font-bold text-white">● مباشر</span>{faces.map((face, index) => <div key={index} className={`pointer-events-none absolute border-2 ${face.matched ? "border-green-400" : "border-red-400"}`} style={{ left: `${face.left / size.width * 100}%`, top: `${face.top / size.height * 100}%`, width: `${(face.right - face.left) / size.width * 100}%`, height: `${(face.bottom - face.top) / size.height * 100}%` }}><span className={`absolute bottom-full right-0 whitespace-nowrap rounded px-2 py-1 text-xs text-white ${face.matched ? "bg-green-700" : "bg-red-700"}`}>{face.matched ? `${face.student_name ?? "طالب"} · تشابه ${Math.round(face.confidence * 100)}%` : face.reason === "face_too_small" ? "الوجه صغير: اقترب أو عدّل الكاميرا" : "لا يوجد تطابق واضح"}</span></div>)}</> : <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center text-gray-300"><Camera className="mb-4 h-12 w-12" /><p>{state === "starting" ? "جاري تجهيز التعرف وفتح الكاميرا..." : "ابدأ التسجيل واسمح باستخدام الكاميرا"}</p></div>}</div>
      </section>
    </div>
  </div>;
}
