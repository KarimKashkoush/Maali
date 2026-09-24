"use client";
import Image from "next/image";
import logo from "../../../../assets/images/logo.png";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import InstallApp from "../../InstallApp";
import { apiFetch, errorMessage } from "@/Api/client";
export default function Navbar() {
  const path = usePathname();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function logout() {
    setBusy(true); setError(null);
    try { await apiFetch("/auth/logout", { method: "POST" }); window.location.assign("/login"); }
    catch (requestError) { setError(errorMessage(requestError)); setBusy(false); }
  }
  return <header className="mb-10 border-b bg-white py-3"><nav className="container flex flex-wrap items-center justify-between gap-4" aria-label="القائمة الرئيسية">
    <Link href="/"><Image src={logo} alt="معالي — الحضور المدرسي" width={150} height={50} priority /></Link>
    <InstallApp />
    {path !== "/login" && <div className="flex flex-wrap items-center gap-4 text-sm font-semibold text-[#0F4C3A]">
      <Link href="/">السبورة</Link><Link href="/classrooms">الفصول</Link><Link href="/student">الطلاب</Link><Link href="/manage">الإدارة</Link>
      <button onClick={logout} disabled={busy} className="rounded-lg border px-3 py-2 disabled:opacity-50">{busy ? "جاري الخروج..." : "تسجيل الخروج"}</button>
    </div>}
    {error && <p role="alert" className="w-full text-sm text-red-600">{error}</p>}
  </nav></header>;
}
