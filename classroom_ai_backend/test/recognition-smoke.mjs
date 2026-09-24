// Optional full-stack self-match smoke test. Uses a user-provided local photo;
// does not bundle photos or measure identification accuracy across people.
import assert from 'node:assert/strict';
import {readFile,mkdtemp,rm} from 'node:fs/promises';
import {randomBytes} from 'node:crypto';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import pg from 'pg';
import {loadConfig} from '../src/config.js';
import {migrate} from '../src/migrate.js';
import {createApp} from '../src/app.js';
const photoPath=process.argv[2];
if(!photoPath || !process.env.TEST_DATABASE_URL || !new URL(process.env.TEST_DATABASE_URL).pathname.endsWith('_test'))throw new Error('Supply local photo path and dedicated TEST_DATABASE_URL ending _test');
const schema='smoke_'+randomBytes(6).toString('hex');
const control=new pg.Pool({connectionString:process.env.TEST_DATABASE_URL});
const storageDir=await mkdtemp(join(tmpdir(),'classroom-smoke-'));
await control.query(`CREATE SCHEMA ${schema}`);
const pool=new pg.Pool({connectionString:process.env.TEST_DATABASE_URL,options:`-c search_path=${schema}`});
let server;
try {
 await migrate(pool);
 const config={...loadConfig(),storageProvider:'local',storageDir};
 const app=createApp({pool,config,now:()=>new Date('2026-09-23T05:05:00Z')});
 server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 const base=`http://127.0.0.1:${server.address().port}/api/v1`;let cookie='';
 async function request(path,method='GET',body){const headers={cookie};if(body && !(body instanceof FormData))headers['content-type']='application/json';const response=await fetch(base+path,{method,headers,body:body instanceof FormData?body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw new Error(`${path} ${response.status}: ${JSON.stringify(data)}`);if(response.headers.get('set-cookie'))cookie=response.headers.get('set-cookie').split(';')[0];return data;}
 await request('/auth/login','POST',{username:config.adminUsername,password:config.adminPassword});
 const school=await request('/schools','POST',{name:'اختبار الربط المحلي',timezone:'Asia/Riyadh'});
 const stage=await request('/stages','POST',{school_id:school.id,name:'مرحلة الاختبار'});
 const classroom=await request('/classrooms','POST',{school_id:school.id,stage_id:stage.id,classroom_name:'فصل الاختبار',attendance_start:'08:00',grace_minutes:10,absence_after_minutes:30,attendance_end:'14:00',weekdays:[0,1,2,3,4]});
 const bytes=await readFile(photoPath);const form=new FormData();form.append('full_name','طالب اختبار مؤقت');form.append('class_id',String(classroom.id));form.append('photo',new Blob([bytes]),'test.jpg');
 const student=await request('/students','POST',form);assert.equal(student.students_images.length,1);
 const session=await request('/attendance/live/start','POST',{class_id:classroom.id,camera_mode:'browser'});
 assert.equal(session.enrolled_students,1);
 for(let i=0;i<3;i++){const frame=new FormData();frame.append('frame',new Blob([bytes]),'frame.jpg');const result=await request(`/attendance/live/frame/${session.session_id}`,'POST',frame);assert.ok(result.detections.some(d=>d.matched&&d.student_id===student.id));}
 const day=await request(`/attendance/daily/class/${classroom.id}`);assert.equal(day.records[0].status,'present');
 assert.equal(day.records[0].check_in_at,'2026-09-23T05:05:00.000Z');
 await request(`/attendance/live/stop/${session.session_id}`,'POST');
 console.log('PASS: real photo -> Node upload -> Python embedding -> PostgreSQL -> 3 real Python matches -> attendance present. Temporary records and copy removed. This is a self-match smoke test, not an accuracy benchmark.');
} finally {
 if(server)await new Promise(r=>server.close(r));
 await pool.end();
 if(!/^smoke_[0-9a-f]{12}$/.test(schema))throw new Error('Unsafe test schema');
 await control.query(`DROP SCHEMA ${schema} CASCADE`);await control.end();
 await rm(storageDir,{recursive:true,force:true});
}
