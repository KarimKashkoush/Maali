import { apiJson } from "./client";
import type { Student } from "./types";
export function getStudents(classId?: number) { return apiJson<Student[]>(`/students?include_inactive=true${classId ? `&class_id=${classId}` : ""}`); }
