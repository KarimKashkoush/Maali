export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`/api/backend${path}`, { ...init, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.error?.message ?? body?.message ?? body?.detail;
    if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    throw new ApiError(typeof message === "string" ? message : "تعذر إتمام الطلب. حاول مرة أخرى.", response.status);
  }
  return response;
}
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> { return (await apiFetch(path, init)).json() as Promise<T>; }
export function jsonBody(value: unknown): Pick<RequestInit, "headers" | "body"> {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) };
}
export function errorMessage(error: unknown): string { return error instanceof Error ? error.message : "حدث خطأ غير متوقع. حاول مرة أخرى."; }
export function privateImageUrl(id: number): string { return `/api/backend/images/${id}/content`; }
