import { apiJson } from "./client";
import type { School } from "./types";
export function getSchools() { return apiJson<School[]>("/schools"); }
