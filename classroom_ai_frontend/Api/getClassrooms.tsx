import { apiJson } from "./client";
import type { Classroom } from "./types";
export function getClassrooms() { return apiJson<Classroom[]>("/classrooms"); }
