"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";

const CountUp = dynamic(() => import("react-countup"), {
    ssr: false,
});
import { motion } from "framer-motion";

import { Classroom } from "@/types/school";
import Link from "next/link";
interface ClassroomCardProps {
    classroom: Classroom;
    selectForBoard?: boolean;
    onSelect?: (classroomId: number) => void;
}

export default function ClassroomCard({
    classroom,
    selectForBoard = false,
    onSelect,
}: ClassroomCardProps) {
    // Stable object reference prevents Framer Motion from restarting the animation on parent re-renders
    const progressAnimate = useMemo(
        () => ({ width: `${classroom.summary.attendanceRate}%` }),
        [classroom.summary.attendanceRate]
    );

    const card = (
                <div className="rounded-xl border p-3 shadow">
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="text-md font-bold text-[#0F4C3A]">
                            {classroom.name}
                        </h2>

                        {classroom.summary.totalAbsent === 0 ? (
                            <span className="text-[#0F4C3A] bg-[#0F4C3A50] text-sm px-2 rounded-full">
                                لا غياب مسجل
                            </span>
                        ) : (
                            <span className="text-[#ad4a03] bg-[#ad4a0350] text-sm px-2 rounded-full">
                                <CountUp end={classroom.summary.totalAbsent} duration={1.5} /> غائب
                            </span>
                        )}
                    </div>

                    {/* Progress */}
                    <div className="h-2 w-full mt-3 overflow-hidden rounded-full bg-gray-200">
                        <motion.div
                            className="h-full rounded-full bg-[#ad4a03]"
                            initial={{ width: 0 }}
                            animate={progressAnimate}
                            transition={{
                                duration: 1.5,
                                ease: "easeOut",
                            }}
                        />
                    </div>

                    <div className="flex justify-between mt-3">
                        <span className="text-sm">
                            <CountUp
                                end={classroom.summary.totalPresent}
                                duration={1.5}
                            />{" "}
                            من{" "}
                            <CountUp
                                end={classroom.summary.totalStudents}
                                duration={1.5}
                            />
                        </span>

                        <span className="text-sm">
                            <CountUp
                                end={classroom.summary.attendanceRate}
                                duration={1.5}
                            />
                            % حضور
                        </span>
                    </div>
                </div>
    );

    if (selectForBoard) {
        return (
            <button
                type="button"
                onClick={() => onSelect?.(classroom.id)}
                className="block w-full text-right transition hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-[#0F4C3A] rounded-xl"
            >
                {card}
            </button>
        );
    }

    return <Link href={`/classroom/${classroom.id}`} className="block">{card}</Link>;
}
