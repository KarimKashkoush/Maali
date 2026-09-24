"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ErrorNotice } from "./ApiStatus";
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (path === "/login") return;
    const abort = new AbortController();
    fetch("/api/backend/auth/me", { credentials: "same-origin", cache: "no-store", signal: abort.signal })
      .then(async (response) => {
        if (response.status === 401) { router.replace(`/login?next=${encodeURIComponent(path)}`); return; }
        if (!response.ok) throw new Error("تعذر الاتصال بخادم المدرسة. أعد المحاولة بعد تشغيله.");
        setError(null); setReady(true);
      }).catch((requestError) => { if (!abort.signal.aborted) setError(requestError.message); });
    return () => abort.abort();
  }, [path, router]);
  if (path === "/login") return children;
  if (error) return <div className="py-10"><ErrorNotice message={error} /><button onClick={() => window.location.reload()} className="underline">إعادة المحاولة</button></div>;
  return ready ? children : <p className="py-20 text-center text-gray-500">جاري التحقق من تسجيل الدخول...</p>;
}
