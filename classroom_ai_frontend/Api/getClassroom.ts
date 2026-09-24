import { apiJson } from "./client";
import type { Classroom } from "./types";
export function getClassroom(id: number) { return apiJson<Classroom>(`/classrooms/${id}`); }
