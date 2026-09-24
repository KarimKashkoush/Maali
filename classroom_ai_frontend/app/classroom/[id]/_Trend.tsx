"use client";

import { useState } from "react";
import { TrendingUp } from "lucide-react";
import { ResponsiveContainer } from "recharts";
import {
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  XAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

const chartData = [
  { day: "الأحد", attendance: 98, absence: 2 },
  { day: "الإثنين", attendance: 88, absence: 12 },
  { day: "الثلاثاء", attendance: 78, absence: 22 },
  { day: "الأربعاء", attendance: 90, absence: 10 },
  { day: "الخميس", attendance: 95, absence: 5 },
];

const chartConfig = {
  attendance: {
    label: "نسبة الحضور",
    color: "#22c55e",
  },
  absence: {
    label: "نسبة الغياب",
    color: "#ef4444",
  },
} satisfies ChartConfig;

export function ChartLineLabel() {
  const [chartType, setChartType] = useState<"attendance" | "absence">(
    "attendance"
  );

  return (
    <Card className="max-w-[450px]">
      <CardHeader>
        <CardTitle>إحصائيات الحضور الأسبوعية</CardTitle>
        <CardDescription>
          اختر بين نسبة الحضور أو نسبة الغياب
        </CardDescription>
      </CardHeader>

      <CardContent>
        {/* Buttons */}
        <div className="mb-6 flex gap-3">
          <button
            onClick={() => setChartType("attendance")}
            className={`rounded-lg px-4 py-2 transition font-medium ${chartType === "attendance"
              ? "bg-green-600 text-white"
              : "bg-gray-200 hover:bg-gray-300"
              }`}
          >
            نسبة الحضور
          </button>

          <button
            onClick={() => setChartType("absence")}
            className={`rounded-lg px-4 py-2 transition font-medium ${chartType === "absence"
              ? "bg-red-600 text-white"
              : "bg-gray-200 hover:bg-gray-300"
              }`}
          >
            نسبة الغياب
          </button>
        </div>

        <ChartContainer
          config={chartConfig}
          className="h-[250px] max-w-[400px] mx-auto"
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{
                top: 20,
                left: 20,
                right: 20,
                bottom: 10,
              }}
            >
              <CartesianGrid vertical={false} />

              <XAxis
                dataKey="day"
                tickLine={false}
                axisLine={false}
                tickMargin={10}
                interval={0}
                height={40}
              />

              <ChartTooltip
                cursor={false}
                content={<ChartTooltipContent indicator="line" />}
              />

              <Line
                type="natural"
                dataKey={chartType}
                stroke={
                  chartType === "attendance"
                    ? "#22c55e"
                    : "#ef4444"
                }
                strokeWidth={3}
                dot={{
                  fill:
                    chartType === "attendance"
                      ? "#22c55e"
                      : "#ef4444",
                }}
                activeDot={{
                  r: 7,
                }}
              >
                <LabelList
                  dataKey={chartType}
                  position="top"
                  offset={10}
                  className="fill-foreground"
                  fontSize={12}
                />
              </Line>
            </LineChart>
          </ResponsiveContainer>
        </ChartContainer>
      </CardContent>

      <CardFooter className="flex-col items-start gap-2 text-sm">
        <div className="flex items-center gap-2 font-medium">
          <TrendingUp className="h-4 w-4" />
          {chartType === "attendance"
            ? "يعرض نسبة الحضور لكل يوم"
            : "يعرض نسبة الغياب لكل يوم"}
        </div>

        <div className="text-muted-foreground">
          بيانات الأسبوع الحالي
        </div>
      </CardFooter>
    </Card>
  );
}