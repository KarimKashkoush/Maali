import { fail } from './errors.js';
export function recognitionClient(config) {
 async function ready() {
  try {
   const response = await fetch(`${config.recognitionUrl}/health`, {signal:AbortSignal.timeout(5000)});
   const data = await response.json();
   if(response.ok && data.status === 'ok' && data.model === 'dlib-v1') return;
  } catch { /* Report an actionable error before the browser opens its camera. */ }
  fail(503,'خدمة التعرف على الصور غير متاحة. شغّل خدمة Python ثم اضغط بدء التسجيل مرة أخرى.');
 }
 async function call(path,field,bytes,candidates) {
  const form = new FormData(); form.append(field,new Blob([bytes],{type:'image/jpeg'}),'image.jpg');
  if(candidates) form.append('candidates',JSON.stringify(candidates));
  let response;
  try { response = await fetch(`${config.recognitionUrl}${path}`,{method:'POST',headers:{'X-Recognition-Key':config.recognitionKey},body:form,signal:AbortSignal.timeout(45000)}); }
  catch { fail(503,'خدمة التعرف على الصور غير متاحة، حاول مرة أخرى.'); }
  const data = await response.json().catch(()=>({}));
  if(!response.ok) {
   if([400,413,415,422].includes(response.status))fail(422,'تعذر التعرف من الصورة؛ استخدم صورة واضحة لوجه واحد بصيغة JPEG أو PNG أو WebP.');
   if(response.status===429)fail(503,'خدمة الصور مشغولة، حاول بعد لحظات.');
   fail(503,'خدمة التعرف غير متاحة حاليًا، حاول مرة أخرى.');
  }
  return data;
 }
 return {ready,enroll:bytes=>call('/internal/enroll','photo',bytes),recognize:(bytes,candidates)=>call('/internal/recognize','frame',bytes,candidates)};
}
