"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Classrooms from "./_components/classrooms/Classrooms";

const BOARD_CLASSROOM_KEY = "classroom-ai:board-classroom-id";

export default function Home() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const classroomId = window.localStorage.getItem(BOARD_CLASSROOM_KEY);
    if (classroomId) {
      router.replace(`/classroom/${classroomId}`);
      return;
    }
    const timer = window.setTimeout(() => setReady(true), 0);
    return () => window.clearTimeout(timer);
  }, [router]);

  if (!ready) {
    return <div className="py-20 text-center text-gray-500">جاري فتح فصل السبورة...</div>;
  }

  return (
    <div className="flex flex-col justify-between py-12" suppressHydrationWarning>
      <div className="mb-6 rounded-3xl border border-[#0F4C3A30] bg-white p-5 text-center shadow-sm">
        <h1 className="text-2xl font-bold text-[#0F4C3A]">إعداد سبورة الفصل</h1>
        <p className="mt-2 text-sm text-gray-500">اختر الفصل مرة واحدة؛ ستفتح هذه السبورة عليه تلقائيًا بعد ذلك.</p>
      </div>
      <Classrooms
        boardSetup
        onClassroomSelect={(classroomId) => {
          window.localStorage.setItem(BOARD_CLASSROOM_KEY, String(classroomId));
          router.push(`/classroom/${classroomId}`);
        }}
      />
    </div>
  );
}
