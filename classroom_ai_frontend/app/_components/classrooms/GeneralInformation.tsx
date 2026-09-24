"use client";

import dynamic from "next/dynamic";

const CountUp = dynamic(() => import("react-countup"), {
    ssr: false,
});
import { motion } from "framer-motion";

interface GeneralInformationProps {
    information: {
        name: string;
        summary: {
            attendanceRate: number;
            totalStudents: number;
            totalPresent: number;
            totalAbsent: number;
            totalClasses: number;
            activeClasses: number;
        };
    };
    showClasses?: boolean;
}



export default function GeneralInformation({
    information,
    showClasses,
}: GeneralInformationProps) {
    return (
        <section className="rounded-2xl bg-[#0F4C3A] text-white p-4 shadow-lg mb-7">
            <div className="flex items-center justify-between mb-8">
                <h1 className="text-4xl font-bold">{information.name}</h1>

                <div className="text-center">
                    <p className="text-5xl font-bold">
                        <CountUp end={information.summary.attendanceRate} duration={1.5} />%
                    </p>
                </div>
            </div>

            <div
                className={`grid gap-6 text-center mb-3 ${showClasses
                    ? "grid-cols-2 lg:grid-cols-5"
                    : "grid-cols-3"
                    }`}
            >
                <div>
                    <h3 className="text-sm opacity-70">
                        إجمالي الطلاب
                    </h3>

                    <p className="text-3xl font-bold">
                        <CountUp end={information.summary.totalStudents} duration={1.5} />
                    </p>
                </div>

                <div>
                    <h3 className="text-sm opacity-70">
                        الحاضرون
                    </h3>

                    <p className="text-3xl font-bold text-green-300">
                        <CountUp end={information.summary.totalPresent} duration={1.5} />
                    </p>
                </div>

                <div>
                    <h3 className="text-sm opacity-70">
                        الغائبون
                    </h3>

                    <p className="text-3xl font-bold text-yellow-300">
                        <CountUp end={information.summary.totalAbsent} duration={1.5} />
                    </p>
                </div>

                {showClasses && (
                    <>
                        <div>
                            <h3 className="text-sm opacity-70">
                                عدد الفصول
                            </h3>

                            <p className="text-3xl font-bold">
                                <CountUp end={information.summary.totalClasses} duration={1.5} />
                            </p>
                        </div>

                        <div>
                            <h3 className="text-sm opacity-70">
                                الفصول النشطة
                            </h3>

                            <p className="text-3xl font-bold">
                                <CountUp end={information.summary.activeClasses} duration={1.5} />
                            </p>
                        </div>
                    </>
                )}

            </div>

            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
                <motion.div
                    className="h-full rounded-full bg-[#ad4a03]"
                    initial={{ width: 0 }}
                    animate={{ width: `${information.summary.attendanceRate}%` }}
                    transition={{
                        duration: 1.5,
                        ease: "easeOut",
                    }}
                />
            </div>
        </section>
    )
}
