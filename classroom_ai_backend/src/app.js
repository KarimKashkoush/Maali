import express from 'express';
import helmet from 'helmet';
import multer from 'multer';
import {rateLimit} from 'express-rate-limit';
import {z} from 'zod';
import {DateTime} from 'luxon';
import {setupAuth} from './auth.js';
import {fail,one,transaction} from './errors.js';
import {createStorage,sanitizePhoto} from './storage.js';
import {recognitionClient} from './recognition.js';
import {daily,ensureDay,getClass,localNow,mark,saveScheduleVersion,applyScheduleToday} from './attendance.js';

const name=z.string().trim().min(2).max(150);
const id=z.coerce.number().int().positive().max(2147483647);
const schoolSchema=z.object({name,school_type:z.enum(['boys','girls','kindergarten']).nullable().optional(),curriculum:z.enum(['national','international']).nullable().optional(),timezone:z.string().refine(v=>DateTime.now().setZone(v).isValid,'توقيت المدرسة غير صالح').default('Asia/Riyadh')}).strict();
const stageSchema=z.object({school_id:id,name}).strict();
const clock=z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/);
const classSchema=z.object({school_id:id,stage_id:id,classroom_name:name,attendance_start:clock.default('07:00'),grace_minutes:z.number().int().min(0).max(180).default(10),absence_after_minutes:z.number().int().min(0).max(360).default(30),attendance_end:clock.default('14:00'),weekdays:z.array(z.number().int().min(0).max(6)).min(1).max(7).default([0,1,2,3,4])}).strict();
const imageType=z.enum(['primary','front','left','right','up','down']);
function validSchedule(data) {
 const minutes=t=>Number(t.slice(0,2))*60+Number(t.slice(3,5));
 if(minutes(data.attendance_end)<=minutes(data.attendance_start)+data.absence_after_minutes || data.absence_after_minutes<data.grace_minutes)fail(422,'موعد الانصراف يجب أن يكون بعد مهلة الغياب، ومهلة الغياب بعد فترة السماح');
 data.weekdays=[...new Set(data.weekdays)]; return data;
}
const imageDto=row=>({id:row.id,student_id:row.student_id,type:row.type,is_primary:row.type==='primary',image_url:`/api/backend/images/${row.id}/content`,created_at:row.created_at});

export function createApp({pool,config,recognition=recognitionClient(config),now=()=>new Date()}) {
 const app=express();
 app.disable('x-powered-by');
 app.use(helmet());
 // Only a Next same-origin proxy calls this API. No public CORS or public storage.
 app.use(express.json({limit:'64kb'}));
 app.get('/health',async(_req,res)=>{await pool.query('SELECT 1');res.json({status:'ok',service:'classroom-node',database:'postgresql'});});
 setupAuth(app,pool,config);
 const api=express.Router(); app.use('/api/v1',api);
 api.use(rateLimit({windowMs:60000,limit:600,standardHeaders:'draft-8',legacyHeaders:false,message:{detail:'طلبات كثيرة، حاول لاحقًا'}}));
 const upload=multer({storage:multer.memoryStorage(),limits:{fileSize:config.maxImageBytes||5242880,files:1,fields:8,fieldSize:2048}});
 const storage=createStorage(config);
 const live=new Map();
 const pathId=req=>id.parse(req.params.id);
 async function audit(db,req,action,entityId,details={}) {await db.query('INSERT INTO audit_log(actor,action,entity_id,details) VALUES($1,$2,$3,$4)',[req.actor,action,entityId,JSON.stringify(details)]);}
 function invalidateClass(classId) {for(const [key,state]of live)if(state.classId===classId)live.delete(key);}
 async function studentDto(student,db=pool) {
  const images=(await db.query('SELECT id,student_id,type,created_at FROM student_images WHERE student_id=$1 ORDER BY id',[student.id])).rows.map(imageDto);
  const classroom=await getClass(db,student.class_id);
  const records=(await db.query('SELECT r.*,d.attendance_date::text AS attendance_date FROM attendance_records r JOIN attendance_days d ON d.id=r.day_id WHERE r.student_id=$1 ORDER BY d.attendance_date DESC LIMIT 90',[student.id])).rows;
  return {...student,name:student.full_name,external_student_id:student.id,classrooms:classroom,students_images:images,photo_url:images.find(x=>x.is_primary)?.image_url||images[0]?.image_url||null,attendance_records:records};
 }
 async function classroomDto(row,includeStudents=false) {
  const day=await daily(pool,row.id,null,now);
  const records=day.records;
  const stats={total_students:records.length,total_present:records.filter(r=>['present','late'].includes(r.status)).length,total_late:records.filter(r=>r.status==='late').length,total_absent:records.filter(r=>r.status==='absent').length,total_pending:records.filter(r=>r.status==='pending').length,attendance_rate:0};
  stats.attendance_rate=records.length?Math.round(stats.total_present/records.length*100):0;
  const output={...row,statistics:stats,classroom_statistics_classroom_id_fkey:stats};
  if(includeStudents)output.students=await Promise.all((await pool.query('SELECT * FROM students WHERE class_id=$1 AND is_active=true ORDER BY full_name',[row.id])).rows.map(s=>studentDto(s)));
  return output;
 }
 api.get('/schools',async(_req,res)=>{
  const schools=(await pool.query('SELECT * FROM schools ORDER BY id')).rows;
  const stages=(await pool.query('SELECT * FROM stages ORDER BY id')).rows;
  const classes=await Promise.all((await pool.query('SELECT * FROM classrooms ORDER BY id')).rows.map(c=>classroomDto(c)));
  for(const school of schools) {
   const mine=classes.filter(c=>c.school_id===school.id);
   school.school_name=school.name;
   school.stage=stages.filter(s=>s.school_id===school.id).map(s=>({...s,stage_name:s.name,classrooms:mine.filter(c=>c.stage_id===s.id)}));
   school.school_statistics={total_classes:mine.length,active_classes:mine.length,total_students:0,total_present:0,total_absent:0,total_pending:0,total_late:0,attendance_rate:0};
   for(const c of mine)for(const key of ['total_students','total_present','total_absent','total_pending','total_late'])school.school_statistics[key]+=c.statistics[key];
   if(school.school_statistics.total_students)school.school_statistics.attendance_rate=Math.round(school.school_statistics.total_present/school.school_statistics.total_students*100);
  }
  res.json(schools);
 });
 api.post('/schools',async(req,res)=>{const data=schoolSchema.parse(req.body);const row=await one(pool,'INSERT INTO schools(name,timezone,school_type,curriculum) VALUES($1,$2,$3,$4) RETURNING *',[data.name,data.timezone,data.school_type??null,data.curriculum??null]);await audit(pool,req,'school.create',row.id);res.status(201).json(row);});
 api.patch('/schools/:id',async(req,res)=>{
  const data=schoolSchema.partial().parse(req.body);if(!Object.hasOwn(req.body,'timezone'))delete data.timezone;const old=await one(pool,'SELECT * FROM schools WHERE id=$1',[pathId(req)]);
  const row=await transaction(pool,async db=>{
   const updated=await one(db,'UPDATE schools SET name=$1,timezone=$2,school_type=$3,curriculum=$4 WHERE id=$5 RETURNING *',[data.name??old.name,data.timezone??old.timezone,data.school_type===undefined?old.school_type:data.school_type,data.curriculum===undefined?old.curriculum:data.curriculum,old.id]);
   if(updated.timezone!==old.timezone)for(const classroom of (await db.query('SELECT * FROM classrooms WHERE school_id=$1',[old.id])).rows)await saveScheduleVersion(db,{...classroom,timezone:updated.timezone},localNow(now,old.timezone).plus({days:1}).toISODate());
   await audit(db,req,'school.update',old.id);return updated;
  });res.json(row);
 });
 api.get('/stages',async(_req,res)=>res.json((await pool.query('SELECT * FROM stages ORDER BY id')).rows));
 api.post('/stages',async(req,res)=>{const data=stageSchema.parse(req.body);res.status(201).json(await one(pool,'INSERT INTO stages(school_id,name) VALUES($1,$2) RETURNING *',[data.school_id,data.name]));});
 api.patch('/stages/:id',async(req,res)=>{const data=z.object({name}).strict().parse(req.body);res.json(await one(pool,'UPDATE stages SET name=$1 WHERE id=$2 RETURNING *',[data.name,pathId(req)]));});
 api.get('/classrooms',async(_req,res)=>res.json(await Promise.all((await pool.query('SELECT * FROM classrooms ORDER BY id')).rows.map(c=>classroomDto(c)))));
 api.get('/classrooms/:id',async(req,res)=>res.json(await classroomDto(await getClass(pool,pathId(req)),true)));
 api.post('/classrooms',async(req,res)=>{
  const d=validSchedule(classSchema.parse(req.body));
  const row=await transaction(pool,async db=>{
   const created=await one(db,'INSERT INTO classrooms(school_id,stage_id,classroom_name,attendance_start,grace_minutes,absence_after_minutes,attendance_end,weekdays) VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *',[d.school_id,d.stage_id,d.classroom_name,d.attendance_start,d.grace_minutes,d.absence_after_minutes,d.attendance_end,d.weekdays]);
   const classroom=await getClass(db,created.id);await saveScheduleVersion(db,classroom,localNow(now,classroom.timezone).toISODate());await audit(db,req,'classroom.create',created.id);return created;
  });res.status(201).json(row);
 });
 api.patch('/classrooms/:id',async(req,res)=>{
  const {schedule_effective,...body}=z.object({schedule_effective:z.enum(['today','tomorrow']).default('tomorrow')}).passthrough().parse(req.body);
  const patch=classSchema.partial().parse(body);for(const key of Object.keys(patch))if(!Object.hasOwn(req.body,key))delete patch[key];const old=await getClass(pool,pathId(req));
  const d=validSchedule({...old,attendance_start:old.attendance_start.slice(0,5),attendance_end:old.attendance_end.slice(0,5),...patch});
  const row=await transaction(pool,async db=>{
   const updated=await one(db,'UPDATE classrooms SET school_id=$1,stage_id=$2,classroom_name=$3,attendance_start=$4,grace_minutes=$5,absence_after_minutes=$6,attendance_end=$7,weekdays=$8 WHERE id=$9 RETURNING *',[d.school_id,d.stage_id,d.classroom_name,d.attendance_start,d.grace_minutes,d.absence_after_minutes,d.attendance_end,d.weekdays,old.id]);
   const classroom=await getClass(db,old.id);
   let changes;
   if(schedule_effective==='today')changes=await applyScheduleToday(db,classroom,now);
   else await saveScheduleVersion(db,classroom,localNow(now,old.timezone).plus({days:1}).toISODate());
   await audit(db,req,'classroom.update',old.id,{schedule_effective,...changes});return updated;
  });invalidateClass(row.id);res.json(row);
 });
 api.get('/students',async(req,res)=>{
  const args=req.query.class_id?[id.parse(req.query.class_id)]:[];
  const includeInactive=req.query.include_inactive===undefined?false:z.enum(['true','false']).parse(req.query.include_inactive)==='true';
  const {rows}=await pool.query('SELECT * FROM students WHERE '+(includeInactive?'true':'is_active=true')+(args.length?' AND class_id=$1':'')+' ORDER BY full_name',args);
  res.json(await Promise.all(rows.map(s=>studentDto(s))));
 });
 api.get('/students/:id',async(req,res)=>res.json(await studentDto(await one(pool,'SELECT * FROM students WHERE id=$1',[pathId(req)]))));
 async function preparedPhoto(req) {
  if(!req.file)fail(422,'صورة واحدة على الأقل مطلوبة للطالب');
  const bytes=await sanitizePhoto(req.file.buffer);const result=await recognition.enroll(bytes);
  if(!Array.isArray(result.embedding)||result.embedding.length!==128||result.embedding.some(v=>typeof v!=='number'||!Number.isFinite(v)))fail(502,'نتيجة التعرف غير صالحة');
  return {bytes,embedding:result.embedding,model:result.model||'dlib-v1'};
 }
 api.post('/students',upload.single('photo'),async(req,res)=>{
  const data=z.object({full_name:name,class_id:id}).strict().parse(req.body);const classroom=await getClass(pool,data.class_id);
  const photo=req.file?await preparedPhoto(req):null;const key=photo?await storage.put(photo.bytes):null;
  let student;
  try {student=await transaction(pool,async db=>{
   const row=await one(db,'INSERT INTO students(full_name,class_id,created_at,updated_at) VALUES($1,$2,$3,$3) RETURNING *',[data.full_name,data.class_id,now()]);
   await db.query('INSERT INTO student_enrollments(student_id,class_id,enrolled_on) VALUES($1,$2,$3)',[row.id,row.class_id,localNow(now,classroom.timezone).toISODate()]);
   if(photo)await db.query("INSERT INTO student_images(student_id,type,storage_key,embedding,model) VALUES($1,'primary',$2,$3,$4)",[row.id,key,JSON.stringify(photo.embedding),photo.model]);
   await audit(db,req,'student.create',row.id,{class_id:row.class_id});return row;
  });} catch(e){if(key)await storage.remove(key).catch(()=>{});throw e;}
  invalidateClass(student.class_id);res.status(201).json(await studentDto(student));
 });
 api.patch('/students/:id',async(req,res)=>{
  const data=z.object({full_name:name.optional(),class_id:id.optional(),is_active:z.boolean().optional()}).strict().parse(req.body);
  const student=await transaction(pool,async db=>{
   const old=await one(db,'SELECT * FROM students WHERE id=$1 FOR UPDATE',[pathId(req)]);
   const next={...old,...data};const classroom=await getClass(db,next.class_id);
   if(next.class_id!==old.class_id||next.is_active!==old.is_active) {
    const oldClass=await getClass(db,old.class_id);
    const oldDay=await ensureDay(db,old.class_id,null,now);
    await db.query("DELETE FROM attendance_records WHERE day_id=$1 AND student_id=$2 AND status IN ('pending','not_scheduled')",[oldDay.id,old.id]);
    await db.query('UPDATE student_enrollments SET withdrawn_on=$1 WHERE student_id=$2 AND withdrawn_on IS NULL',[localNow(now,oldClass.timezone).toISODate(),old.id]);
    if(next.is_active)await db.query('INSERT INTO student_enrollments(student_id,class_id,enrolled_on) VALUES($1,$2,$3)',[old.id,next.class_id,localNow(now,classroom.timezone).toISODate()]);
   }
   const row=await one(db,'UPDATE students SET full_name=$1,class_id=$2,is_active=$3,updated_at=$4 WHERE id=$5 RETURNING *',[next.full_name,next.class_id,next.is_active,now(),old.id]);
   await audit(db,req,'student.update',old.id,{before_class:old.class_id,after_class:row.class_id,is_active:row.is_active});invalidateClass(old.class_id);invalidateClass(row.class_id);return row;
  });res.json(await studentDto(student));
 });
 api.post('/students/:id/images',upload.single('photo'),async(req,res)=>{
  const student=await one(pool,'SELECT * FROM students WHERE id=$1',[pathId(req)]);const type=imageType.parse(req.body.type||'primary');
  const photo=await preparedPhoto(req);const key=await storage.put(photo.bytes);let oldKey;
  let row;
  try {row=await transaction(pool,async db=>{
   await db.query('SELECT id FROM students WHERE id=$1 FOR UPDATE',[student.id]);
   oldKey=(await db.query('SELECT storage_key FROM student_images WHERE student_id=$1 AND type=$2',[student.id,type])).rows[0]?.storage_key;
   const output=await one(db,'INSERT INTO student_images(student_id,type,storage_key,embedding,model) VALUES($1,$2,$3,$4,$5) ON CONFLICT(student_id,type) DO UPDATE SET storage_key=EXCLUDED.storage_key,embedding=EXCLUDED.embedding,model=EXCLUDED.model,created_at=now() RETURNING *',[student.id,type,key,JSON.stringify(photo.embedding),photo.model]);await audit(db,req,'image.save',output.id);return output;
  });}catch(e){await storage.remove(key).catch(()=>{});throw e;}
  if(oldKey)await storage.remove(oldKey).catch(()=>console.warn('Old image cleanup needs retry',row.id));
  invalidateClass(student.class_id);res.status(201).json(imageDto(row));
 });
 api.delete('/students/:id/images/:imageId',async(req,res)=>{
  const removed=await transaction(pool,async db=>{
   const student=await one(db,'SELECT * FROM students WHERE id=$1 FOR UPDATE',[pathId(req)]);
   const images=(await db.query('SELECT * FROM student_images WHERE student_id=$1',[student.id])).rows;
   const target=images.find(i=>i.id===id.parse(req.params.imageId));if(!target)fail(404,'الصورة غير موجودة');
   if(images.length<=1)fail(409,'يجب الاحتفاظ بصورة واحدة على الأقل');
   await db.query('DELETE FROM student_images WHERE id=$1',[target.id]);await audit(db,req,'image.delete',target.id);invalidateClass(student.class_id);return target;
  });await storage.remove(removed.storage_key).catch(()=>console.warn('Deleted image cleanup needs retry',removed.id));res.json({ok:true});
 });
 api.get('/images/:id/content',async(req,res)=>{
  const row=await one(pool,'SELECT storage_key FROM student_images WHERE id=$1',[pathId(req)]);res.set('Cache-Control','private, no-store').type('image/jpeg').send(await storage.get(row.storage_key));
 });
 api.get('/attendance/daily/class/:id',async(req,res)=>res.json(await daily(pool,pathId(req),req.query.date?z.string().parse(req.query.date):null,now)));
 api.patch('/attendance/daily/class/:id/students/:studentId',async(req,res)=>{
  const data=z.object({present:z.boolean()}).strict().parse(req.body);
  res.json(await mark(pool,pathId(req),id.parse(req.params.studentId),data.present,now,req.actor));
 });
 api.post('/attendance/live/start',async(req,res)=>{
  const data=z.object({class_id:id,camera_mode:z.literal('browser').default('browser')}).strict().parse(req.body);
  const day=await daily(pool,data.class_id,null,now);
  if(!day.is_school_day)fail(409,'اليوم ليس من أيام الدراسة');
  const classTime=localNow(now,day.timezone);const time=classTime.toFormat('HH:mm:ss');
  if(time<day.schedule.attendance_start || time>day.schedule.attendance_end)fail(409,'التسجيل خارج مواعيد حضور الفصل');
  const rows=(await pool.query('SELECT s.id,s.full_name,i.embedding FROM students s JOIN student_images i ON i.student_id=s.id WHERE s.class_id=$1 AND s.is_active=true AND i.embedding IS NOT NULL',[data.class_id])).rows;
  const map=new Map();for(const row of rows){if(!map.has(row.id))map.set(row.id,{student_id:row.id,name:row.full_name,embeddings:[]});map.get(row.id).embeddings.push(row.embedding);}
  if(map.size>100)fail(422,'التعرف يدعم حتى 100 طالب في الفصل');
  await recognition.ready();
  for(const[key,state]of live)if(Date.now()-state.lastUsed>30*60000)live.delete(key);
  if(!live.has(day.session_id))live.set(day.session_id,{classId:data.class_id,candidates:[...map.values()],hits:new Map(),busy:false,lastUsed:Date.now()});
  res.json({session_id:day.session_id,status:'active',total_students:day.records.length,enrolled_students:map.size,present_count:day.records.filter(r=>['present','late'].includes(r.status)).length});
 });
 api.post('/attendance/live/stop/:id',async(req,res)=>{
  const day=await one(pool,'SELECT class_id FROM attendance_days WHERE id=$1',[pathId(req)]);live.delete(pathId(req));
  const result=await daily(pool,day.class_id,null,now);res.json({session_id:pathId(req),status:'stopped',present_count:result.records.filter(r=>['present','late'].includes(r.status)).length,absent_count:result.records.filter(r=>r.status==='absent').length});
 });
 api.post('/attendance/live/frame/:id',upload.single('frame'),async(req,res)=>{
  const sessionId=pathId(req);const state=live.get(sessionId);if(!state)fail(409,'ابدأ جلسة الكاميرا من جديد');if(state.busy)fail(429,'جار معالجة اللقطة السابقة');
  if(!req.file)fail(422,'الصورة مطلوبة');state.busy=true;state.lastUsed=Date.now();
  try {
   const buffer=await sanitizePhoto(req.file.buffer);
   const result=await recognition.recognize(buffer,state.candidates.map(({student_id,embeddings})=>({student_id,embeddings})));
   if(live.get(sessionId)!==state)fail(409,'انتهت جلسة الكاميرا');
   if(!Array.isArray(result.detections))fail(502,'نتيجة التعرف غير صالحة');
   const detected=new Set();const names=new Map(state.candidates.map(c=>[c.student_id,c.name]));
   for(const d of result.detections){d.student_name=names.get(d.student_id)||null;if(d.matched && names.has(d.student_id) && Number.isFinite(d.confidence) && d.confidence>=0.62)detected.add(d.student_id);else d.matched=false;}
   for(const key of state.hits.keys())if(!detected.has(key))state.hits.delete(key);
   for(const studentId of detected){const count=(state.hits.get(studentId)||0)+1;state.hits.set(studentId,count);if(count>=(config.recognitionConfirmFrames||3))await mark(pool,state.classId,studentId,true,now,req.actor,result.detections.find(d=>d.student_id===studentId).confidence,'recognition',sessionId);}
   const day=await daily(pool,state.classId,null,now);res.json({...result,present_count:day.records.filter(r=>['present','late'].includes(r.status)).length});
  }finally{state.busy=false;}
 });
 api.get('/audit',async(_req,res)=>res.json((await pool.query('SELECT * FROM audit_log ORDER BY id DESC LIMIT 100')).rows));
 api.use((_req,res)=>res.status(404).json({detail:'المسار غير موجود'}));
 app.use((error,_req,res,_next)=>{
  if(error instanceof z.ZodError)return res.status(422).json({detail:error.issues.map(i=>`${i.path.join('.')}: ${i.message}`).join('، ')});
  if(error instanceof multer.MulterError)return res.status(422).json({detail:'ارفع صورة واحدة بحجم لا يزيد عن 5 ميجابايت'});
  if(error.code==='23503')return res.status(422).json({detail:'المدرسة أو المرحلة أو الفصل غير موجود، أو لا ينتمون لبعضهم'});
  if(error.code==='23505')return res.status(409).json({detail:'هذه البيانات مسجلة بالفعل'});
  if(error.code==='23514')return res.status(422).json({detail:'بيانات أو مواعيد غير صالحة'});
  if(error.type==='entity.parse.failed')return res.status(400).json({detail:'JSON غير صالح'});
  if(error.status)return res.status(error.status).json({detail:error.message});
  console.error('Request failed',error.code||error.name);res.status(500).json({detail:'تعذر تنفيذ الطلب، حاول مرة أخرى'});
 });
 return app;
}
