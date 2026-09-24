import { apiJson } from "./client";
import type { Student } from "./types";
export function getStudent(id: number) { return apiJson<Student>(`/students/${id}`); }
