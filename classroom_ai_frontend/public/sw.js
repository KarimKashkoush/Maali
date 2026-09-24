// Never cache student photos, authenticated pages, API responses or attendance.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
 if (event.request.mode !== 'navigate' || event.request.method !== 'GET') return;
 event.respondWith(fetch(event.request).catch(() => new Response('<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>غياب المعالي</title><body style="font-family:Arial;text-align:center;padding:3rem;background:#F7F5F0;color:#0F4C3A"><h1>غياب المعالي</h1><p>تعذر الاتصال بالخادم. تأكد من الإنترنت ثم أعد المحاولة.</p><p>لم يتم تسجيل حضور أثناء انقطاع الاتصال.</p><a href="/">إعادة المحاولة</a></body></html>', {status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}})));
});
