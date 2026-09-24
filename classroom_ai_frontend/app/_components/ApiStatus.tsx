"use client";
import Link from "next/link";
export const inputClass = "mt-1 w-full rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm focus:border-[#0F4C3A] focus:outline-none focus:ring-2 focus:ring-[#0F4C3A30]";
export const buttonClass = "rounded-xl bg-[#0F4C3A] px-5 py-2.5 font-semibold text-white hover:bg-[#0c3f30] disabled:cursor-not-allowed disabled:opacity-50";
export function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block text-sm font-semibold text-gray-700">{label}{children}</label>; }
export function ErrorNotice({ message }: { message: string | null }) { return message ? <div role="alert" className="my-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{message}</div> : null; }
export function EmptyState({ text }: { text: string }) { return <div className="rounded-2xl border border-dashed p-10 text-center text-gray-500">{text} <Link className="text-[#0F4C3A] underline" href="/manage">فتح الإدارة</Link></div>; }
