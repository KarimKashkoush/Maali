"use client";
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Camera, Upload, Trash2 } from "lucide-react";
import { apiFetch, errorMessage, privateImageUrl } from "@/Api/client";
import type { StudentImage } from "@/Api/types";
import { buttonClass, ErrorNotice } from "../../_components/ApiStatus";
const imageTypes = [{ key: "primary", label: "الصورة الأساسية" }, { key: "front", label: "من الأمام" }, { key: "left", label: "الجانب الأيسر" }, { key: "right", label: "الجانب الأيمن" }, { key: "up", label: "النظر لأعلى" }, { key: "down", label: "النظر لأسفل" }];
export default function StudentImagesForm({ studentImages, studentId, onSaved }: { studentImages: StudentImage[]; studentId: number; onSaved: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [cameraType, setCameraType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const generationRef = useRef(0);
  useEffect(() => () => { generationRef.current++; streamRef.current?.getTracks().forEach((track) => track.stop()); }, []);
  function closeCamera() {
    generationRef.current++; streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraType(null);
  }
  async function openCamera(type: string) {
    closeCamera(); const generation = generationRef.current; setError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("الكاميرا تحتاج متصفحًا يدعمها واتصال HTTPS أو localhost.");
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      if (generation !== generationRef.current) { stream.getTracks().forEach((track) => track.stop()); return; }
      streamRef.current = stream;
      if (!videoRef.current) throw new Error("تعذر فتح نافذة الكاميرا.");
      videoRef.current.srcObject = stream; await videoRef.current.play();
      if (generation === generationRef.current) setCameraType(type);
    } catch (e) { closeCamera(); setError(errorMessage(e)); }
  }
  async function upload(type: string, file?: File) {
    if (!file) return;
    setError(null); setMessage(null);
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024) { setError("اختر صورة JPEG أو PNG أو WebP بحجم لا يزيد عن 5 ميجابايت."); return; }
    setBusy(true);
    try {
      const form = new FormData(); form.append("photo", file); form.append("type", type);
      await apiFetch(`/students/${studentId}/images`, { method: "POST", body: form }); await onSaved(); setMessage("تم حفظ الصورة.");
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function capture() {
    const video = videoRef.current;
    if (!video || !cameraType || !video.videoWidth) return;
    const canvas = document.createElement("canvas"); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) { setError("تعذر التقاط الصورة. حاول مرة أخرى."); return; }
    const type = cameraType; closeCamera(); await upload(type, new File([blob], `${type}.jpg`, { type: "image/jpeg" }));
  }
  async function remove(image: StudentImage) {
    if (studentImages.length <= 1) { setError("يجب الاحتفاظ بصورة واحدة للطالب على الأقل."); return; }
    setBusy(true); setError(null); setMessage(null);
    try { await apiFetch(`/students/${studentId}/images/${image.id}`, { method: "DELETE" }); await onSaved(); setMessage("تم حذف الصورة."); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <section className="mt-8">
    <h2 className="text-2xl font-bold text-[#0F4C3A]">صور التعرف على الطالب</h2>
    <p className="mt-2 text-sm text-gray-500">ابدأ بصورة واضحة، ثم أضف صورًا من الأمام وبميل بسيط يمينًا ويسارًا لتحسين التعرف. اجعل الوجه كبيرًا داخل الصورة والإضاءة أمامه، وتجنب الحركة أثناء الالتقاط. يجب أن يظهر وجه الطالب وحده.</p>
    <ErrorNotice message={error} />{message && <p role="status" className="my-4 text-green-700">{message}</p>}
    <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{imageTypes.map((type) => {
      const image = studentImages.find((item) => item.type === type.key);
      return <article key={type.key} className="rounded-2xl border bg-white p-4">
        <h3 className="mb-3 font-bold">{type.label}</h3>
        <div className="mb-4 flex h-40 items-center justify-center overflow-hidden rounded-xl bg-gray-100">{image ? <Image unoptimized src={`${privateImageUrl(image.id)}?v=${encodeURIComponent(image.created_at ?? "")}`} alt={type.label} width={240} height={160} className="h-full w-full object-contain" /> : <span className="text-sm text-gray-400">لم تُضف صورة</span>}</div>
        <div className="flex flex-wrap gap-2"><label className={`flex cursor-pointer items-center gap-1 rounded-lg bg-[#0F4C3A] px-3 py-2 text-sm text-white ${busy ? "pointer-events-none opacity-50" : ""}`}><Upload size={16} />{image ? "استبدال" : "رفع"}<input disabled={busy} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => { const file = e.currentTarget.files?.[0]; e.currentTarget.value = ""; void upload(type.key, file); }} /></label>
          <button type="button" disabled={busy} onClick={() => openCamera(type.key)} className="flex items-center gap-1 rounded-lg border px-3 py-2 text-sm disabled:opacity-50"><Camera size={16} />كاميرا</button>
          {image && <button type="button" title={studentImages.length <= 1 ? "لا يمكن حذف آخر صورة" : "حذف الصورة"} aria-label={`حذف ${type.label}`} disabled={busy || studentImages.length <= 1} onClick={() => remove(image)} className="rounded-lg border border-red-200 px-3 py-2 text-red-600 disabled:opacity-30"><Trash2 size={16} /></button>}
        </div>
      </article>;
    })}</div>
    <div className={cameraType ? "fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" : "hidden"} role="dialog" aria-modal="true" aria-label="التقاط صورة الطالب">
      <div className="w-full max-w-xl rounded-2xl bg-white p-5"><h3 className="mb-3 text-lg font-bold">ضع وجه الطالب بوضوح داخل الصورة</h3><video ref={videoRef} autoPlay muted playsInline className="w-full rounded-xl bg-black" /><div className="mt-4 flex gap-3"><button type="button" disabled={busy} onClick={capture} className={buttonClass}>التقاط وحفظ</button><button type="button" onClick={closeCamera} className="rounded-xl border px-5 py-2">إلغاء</button></div></div>
    </div>
  </section>;
}
