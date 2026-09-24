import { mkdir,writeFile,readFile,unlink } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import sharp from 'sharp';
import { fail } from './errors.js';
export async function sanitizePhoto(buffer) {
 try {
  const img=sharp(buffer,{limitInputPixels:16000000,failOn:'warning'});
  const meta=await img.metadata();
  if(!['jpeg','png','webp'].includes(meta.format) || (meta.pages||1)>1) fail(422,'استخدم صورة JPEG أو PNG أو WebP غير متحركة');
  return await img.rotate().resize({width:1920,height:1920,fit:'inside',withoutEnlargement:true}).jpeg({quality:90}).toBuffer();
 } catch(e) { if(e.status) throw e; fail(422,'ملف الصورة غير صالح أو حجمه كبير'); }
}
export function createStorage(config) {
 const local=config.storageProvider==='local';
 const headers={'Authorization':`Bearer ${config.supabaseKey}`,apikey:config.supabaseKey};
 const objectUrl=key=>`${config.supabaseUrl}/storage/v1/object/${config.storageBucket}/${key}`;
 return {
  async put(buffer) {
   const key=`${randomUUID()}.jpg`;
   if(local) {await mkdir(config.storageDir,{recursive:true}); await writeFile(path.join(config.storageDir,key),buffer,{flag:'wx'});}
   else { const res=await fetch(objectUrl(key),{method:'POST',headers:{...headers,'Content-Type':'image/jpeg'},body:buffer,signal:AbortSignal.timeout(20000)}); if(!res.ok) fail(503,'تعذر حفظ الصورة في التخزين'); }
   return key;
  },
  async get(key) {
   if(!/^[\da-f-]+\.jpg$/.test(key)) fail(404,'الصورة غير موجودة');
   if(local) {try{return await readFile(path.join(config.storageDir,key));} catch{fail(404,'الصورة غير موجودة');}}
   const res=await fetch(objectUrl(key),{headers,signal:AbortSignal.timeout(20000)}); if(!res.ok) fail(503,'تعذر تحميل الصورة'); return Buffer.from(await res.arrayBuffer());
  },
  async remove(key) {
   if(local) await unlink(path.join(config.storageDir,key)).catch(e=>{if(e.code!=='ENOENT')throw e;});
   else { const res=await fetch(`${config.supabaseUrl}/storage/v1/object/${config.storageBucket}`,{method:'DELETE',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({prefixes:[key]}),signal:AbortSignal.timeout(20000)}); if(!res.ok) throw new Error('Storage cleanup failed'); }
  }
 };
}
