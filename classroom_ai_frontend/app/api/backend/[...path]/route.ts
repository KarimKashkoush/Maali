import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const methodsWithBody = new Set(["POST", "PATCH", "PUT", "DELETE"]);
const maxBodyBytes = 6 * 1024 * 1024;
async function boundedBody(request: NextRequest): Promise<ArrayBuffer | Response> {
  const length = request.headers.get("content-length");
  const tooLarge = () => Response.json({ message: "حجم الطلب كبير جدًا. الحد الأقصى للصورة 5 ميجابايت." }, { status: 413 });
  if (length && (!Number.isFinite(Number(length)) || Number(length) > maxBodyBytes)) return tooLarge();
  const reader = request.body?.getReader();
  if (!reader) return new ArrayBuffer(0);
  let total = 0;
  const chunks: Uint8Array[] = [];
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBodyBytes) { await reader.cancel(); return tooLarge(); }
    chunks.push(value);
  }
  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { combined.set(chunk, offset); offset += chunk.byteLength; }
  return combined.buffer;
}
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!path.length || path.some((part) => part === "." || part === ".." || /[\\/]/.test(part))) {
    return Response.json({ message: "مسار غير صالح" }, { status: 400 });
  }
  const origin = request.headers.get("origin");
  if (methodsWithBody.has(request.method) && origin && origin !== (process.env.APP_ORIGIN ?? process.env.RENDER_EXTERNAL_URL ?? request.nextUrl.origin)) {
    return Response.json({ message: "مصدر الطلب غير مسموح" }, { status: 403 });
  }
  const base = process.env.CLASSROOM_API_URL ?? "http://127.0.0.1:4000/api/v1";
  const target = `${base.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const name of ["content-type", "accept", "cookie"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const body = methodsWithBody.has(request.method) ? await boundedBody(request) : undefined;
    if (body instanceof Response) return body;
    const response = await fetch(target, {
      method: request.method, headers,
      body,
      cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(90_000),
    });
    const outgoing = new Headers({ "Cache-Control": "private, no-store" });
    for (const name of ["content-type", "content-disposition", "retry-after"]) {
      const value = response.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of response.headers.getSetCookie()) outgoing.append("set-cookie", cookie);
    return new Response(response.body, { status: response.status, headers: outgoing });
  } catch {
    return Response.json({ message: "خدمة إدارة المدرسة غير متاحة حاليًا. تأكد من تشغيل الخادم ثم حاول مرة أخرى." }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE, proxy as HEAD };
