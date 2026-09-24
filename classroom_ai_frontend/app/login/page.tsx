"use client";
import { FormEvent, useState } from "react";
import { apiFetch, errorMessage, jsonBody } from "@/Api/client";
import { buttonClass, ErrorNotice, Field, inputClass } from "../_components/ApiStatus";
export default function LoginPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    const data = new FormData(event.currentTarget);
    try {
      await apiFetch("/auth/login", { method: "POST", ...jsonBody({ username: data.get("username"), password: data.get("password") }) });
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.assign(next && /^\/(?!\/)/.test(next) && !next.includes("\\") ? next : "/");
    } catch (requestError) { setError(errorMessage(requestError)); setBusy(false); }
  }
  return <div className="mx-auto max-w-md rounded-3xl border bg-white p-8 shadow-sm">
    <h1 className="text-2xl font-bold text-[#0F4C3A]">تسجيل الدخول</h1><p className="mt-2 text-sm text-gray-500">أدخل حساب إدارة المدرسة للوصول للطلاب والحضور.</p>
    <ErrorNotice message={error} />
    <form onSubmit={submit} className="mt-6 space-y-5">
      <Field label="اسم المستخدم"><input name="username" autoComplete="username" required className={inputClass} /></Field>
      <Field label="كلمة المرور"><input name="password" type="password" autoComplete="current-password" required className={inputClass} /></Field>
      <button disabled={busy} className={buttonClass + " w-full"}>{busy ? "جاري الدخول..." : "دخول"}</button>
    </form>
  </div>;
}
