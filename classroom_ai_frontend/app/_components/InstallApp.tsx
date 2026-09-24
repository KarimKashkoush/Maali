"use client";
import { useEffect, useState } from "react";
type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{outcome: "accepted" | "dismissed"}> };
export default function InstallApp() {
 const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
 const [installed, setInstalled] = useState(false);
 const [help, setHelp] = useState(false);
 useEffect(() => {
  const media = window.matchMedia("(display-mode: standalone)");
  const update = () => setInstalled(media.matches);
  update(); media.addEventListener("change", update);
  const available = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt); };
  const done = () => { setInstalled(true); setPrompt(null); setHelp(false); };
  window.addEventListener("beforeinstallprompt", available);
  window.addEventListener("appinstalled", done);
  if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("/sw.js", {scope:"/"}).catch(() => {});
  return () => { media.removeEventListener("change", update); window.removeEventListener("beforeinstallprompt", available); window.removeEventListener("appinstalled", done); };
 }, []);
 async function install() {
  if (!prompt) { setHelp(value => !value); return; }
  try { await prompt.prompt(); await prompt.userChoice; } catch { setHelp(true); }
  finally { setPrompt(null); }
 }
 if (installed) return null;
 return <div className="text-sm"><button type="button" onClick={install} className="rounded-lg border border-[#0F4C3A] px-3 py-2 font-semibold text-[#0F4C3A]">تثبيت غياب المعالي</button>{help && <p role="status" className="mt-2 max-w-md text-gray-600">افتح الموقع عبر HTTPS في Chrome أو Edge، ثم اختر من قائمة المتصفح «تثبيت التطبيق» أو «إضافة إلى الشاشة الرئيسية». يلزم الاتصال بالخادم لتسجيل الحضور.</p>}</div>;
}
