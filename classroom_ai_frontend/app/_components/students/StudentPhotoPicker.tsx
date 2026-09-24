"use client";
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { errorMessage } from "@/Api/client";
import { ErrorNotice, inputClass } from "../ApiStatus";

export default function StudentPhotoPicker({ file, onChange, disabled }: { file: File | null; onChange: (file: File | null) => void; disabled: boolean }) {
  const [preview, setPreview] = useState("");
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const previewRef = useRef<string | null>(null);
  useEffect(() => () => { generation.current++; stream.current?.getTracks().forEach(track => track.stop()); if (previewRef.current) URL.revokeObjectURL(previewRef.current); }, []);
  useEffect(() => { if (disabled) { generation.current++; stream.current?.getTracks().forEach(track => track.stop()); stream.current = null; } }, [disabled]);
  function close() {
    generation.current++; stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    if (video.current) video.current.srcObject = null;
    setOpen(false); setReady(false); setCapturing(false);
  }
  function choose(next: File | null) {
    setError(null);
    if (next && (!["image/jpeg", "image/png", "image/webp"].includes(next.type) || next.size > 5 * 1024 * 1024)) {
      setError("اختر صورة JPEG أو PNG أو WebP بحجم لا يزيد عن 5 ميجابايت."); return;
    }
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = next ? URL.createObjectURL(next) : null; setPreview(previewRef.current ?? "");
    onChange(next);
  }
  async function start() {
    close(); const current = generation.current; setError(null); setOpen(true);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("الكاميرا تحتاج HTTPS أو localhost ومتصفحًا يدعمها.");
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      if (current !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      if (!video.current) throw new Error("تعذر تجهيز نافذة الكاميرا.");
      video.current.srcObject = media; await video.current.play();
      if (current === generation.current) setReady(true);
    } catch (e) { if (current === generation.current) { close(); setError(errorMessage(e)); } }
  }
  async function capture() {
    if (!stream.current) { close(); setError("افتح الكاميرا مجددًا لالتقاط صورة."); return; }
    if (!video.current?.videoWidth || capturing) return;
    const current = generation.current; setCapturing(true);
    try {
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 1920 / Math.max(video.current.videoWidth, video.current.videoHeight));
      canvas.width = Math.round(video.current.videoWidth * scale); canvas.height = Math.round(video.current.videoHeight * scale);
      canvas.getContext("2d")?.drawImage(video.current, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.9));
      if (current !== generation.current) return;
      if (!blob) throw new Error("تعذر التقاط الصورة. حاول مرة أخرى.");
      choose(new File([blob], "student-camera.jpg", { type: "image/jpeg" })); close();
    } catch (e) { if (current === generation.current) { setError(errorMessage(e)); setCapturing(false); } }
  }
  return <fieldset disabled={disabled} className="space-y-3">
    <legend className="mb-2 font-semibold">صورة الطالب (اختيارية)</legend>
    <p className="text-sm text-gray-500">يمكن الحفظ بدون صورة وتسجيل الحضور يدويًا. التعرف بالكاميرا يحتاج صورة واضحة للوجه ويمكن إضافتها لاحقًا.</p>
    <ErrorNotice message={error} />
    <input aria-label="اختيار صورة الطالب" type="file" accept="image/jpeg,image/png,image/webp" className={inputClass} onChange={event => { choose(event.currentTarget.files?.[0] ?? null); event.currentTarget.value = ""; }} />
    <button type="button" onClick={start} className="rounded-xl border px-4 py-2">التقاط صورة بالكاميرا</button>
    {file && <div><p className="mb-2 text-sm">الصورة المختارة: {file.name}</p>{preview && <Image unoptimized src={preview} alt="معاينة صورة الطالب" width={240} height={180} className="h-44 w-60 rounded-xl object-contain" />}<button type="button" onClick={() => choose(null)} className="mt-2 text-sm text-red-700 underline">إزالة الصورة والحفظ بدونها</button></div>}
    <div hidden={!open} className="rounded-xl border bg-gray-50 p-3">
      <p className="mb-2 text-sm">ضع وجه الطالب وحده داخل الصورة.</p>
      <video ref={video} muted playsInline className="max-h-80 w-full rounded-lg bg-black" />
      <div className="mt-3 flex gap-3"><button type="button" disabled={!ready || capturing || disabled} onClick={capture} className="rounded-lg bg-[#0F4C3A] px-4 py-2 text-white disabled:opacity-50">{capturing ? "جاري الالتقاط..." : "استخدام هذه الصورة"}</button><button type="button" onClick={close} className="rounded-lg border px-4 py-2">إغلاق الكاميرا</button></div>
    </div>
  </fieldset>;
}
