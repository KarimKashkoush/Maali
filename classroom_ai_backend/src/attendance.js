import { DateTime } from 'luxon';
import { fail, one, transaction } from './errors.js';
export function localNow(now,timezone) { return DateTime.fromJSDate(now(),{zone:timezone}); }
export async function getClass(db,id) {return one(db,'SELECT c.*,s.timezone FROM classrooms c JOIN schools s ON s.id=c.school_id WHERE c.id=$1',[id],'الفصل غير موجود');}
export async function saveScheduleVersion(db,classroom,effectiveDate) {
 const schedule={attendance_start:classroom.attendance_start,attendance_end:classroom.attendance_end,grace_minutes:classroom.grace_minutes,absence_after_minutes:classroom.absence_after_minutes,weekdays:classroom.weekdays};
 await db.query('INSERT INTO classroom_schedule_versions(class_id,effective_on,timezone,schedule) VALUES($1,$2,$3,$4) ON CONFLICT(class_id,effective_on) DO UPDATE SET timezone=EXCLUDED.timezone,schedule=EXCLUDED.schedule',[classroom.id,effectiveDate,classroom.timezone,JSON.stringify(schedule)]);
}
export function dayStatus(day,now) {
 const clock=localNow(now,day.timezone);
 const date=String(day.attendance_date).slice(0,10);
 const start=DateTime.fromISO(`${date}T${day.schedule.attendance_start}`,{zone:day.timezone});
 const end=DateTime.fromISO(`${date}T${day.schedule.attendance_end}`,{zone:day.timezone});
 return {clock,start,end,isSchoolDay:day.schedule.weekdays.includes(start.weekday%7),cutoff:start.plus({minutes:day.schedule.absence_after_minutes}),lateAt:start.plus({minutes:day.schedule.grace_minutes})};
}
export async function ensureDay(db,classId,date,now) {
 const classroom=await getClass(db,classId);
 // Class lock serializes roster snapshots and concurrent first check-ins.
 await db.query('SELECT id FROM classrooms WHERE id=$1 FOR UPDATE',[classId]);
 const active=(await db.query('SELECT * FROM classroom_schedule_versions WHERE class_id=$1 AND effective_on <= ($2::timestamptz AT TIME ZONE timezone)::date ORDER BY effective_on DESC LIMIT 1',[classId,now()])).rows[0];
 const today=localNow(now,active?.timezone||classroom.timezone).toISODate();
 date=date||today;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date) || !DateTime.fromISO(date).isValid || date>today) fail(422,'تاريخ الحضور غير صالح');
 const version=(await db.query('SELECT * FROM classroom_schedule_versions WHERE class_id=$1 AND effective_on <= $2::date ORDER BY effective_on DESC LIMIT 1',[classId,date])).rows[0];
 if(!version) fail(422,'هذا التاريخ يسبق إنشاء الفصل');
 await db.query('INSERT INTO attendance_days(class_id,attendance_date,timezone,schedule) VALUES($1,$2,$3,$4) ON CONFLICT(class_id,attendance_date) DO NOTHING',[classId,date,version.timezone,JSON.stringify(version.schedule)]);
 const day=await one(db,'SELECT *,attendance_date::text AS attendance_date FROM attendance_days WHERE class_id=$1 AND attendance_date=$2 FOR UPDATE',[classId,date]);
 const state=dayStatus(day,now);
 const status=!state.isSchoolDay?'not_scheduled':state.clock>=state.cutoff?'absent':'pending';
 await db.query(`INSERT INTO attendance_records(day_id,student_id,student_name,status)
 SELECT $1,s.id,s.full_name,$4 FROM students s JOIN student_enrollments e ON e.student_id=s.id
 WHERE e.class_id=$2 AND e.enrolled_on <= $3::date AND (e.withdrawn_on IS NULL OR e.withdrawn_on > $3::date)
 ON CONFLICT(day_id,student_id) DO NOTHING`,[day.id,classId,date,status]);
 if(status==='absent') await db.query("UPDATE attendance_records SET status='absent',updated_at=$2 WHERE day_id=$1 AND status='pending'",[day.id,now()]);
 return day;
}
// Caller holds the classroom lock; update only today's snapshot and derived statuses.
export async function applyScheduleToday(db,classroom,now) {
 const day=await ensureDay(db,classroom.id,null,now);
 const before=day.schedule;
 const schedule={attendance_start:classroom.attendance_start,attendance_end:classroom.attendance_end,grace_minutes:classroom.grace_minutes,absence_after_minutes:classroom.absence_after_minutes,weekdays:classroom.weekdays};
 await saveScheduleVersion(db,{...classroom,timezone:day.timezone},day.attendance_date);
 // Replace pending schedule values too, while preserving any planned timezone change.
 await db.query('UPDATE classroom_schedule_versions SET schedule=$1 WHERE class_id=$2 AND effective_on>$3::date',[JSON.stringify(schedule),classroom.id,day.attendance_date]);
 await db.query('UPDATE attendance_days SET schedule=$1 WHERE id=$2',[JSON.stringify(schedule),day.id]);
 const state=dayStatus({...day,schedule},now);
 const records=(await db.query('SELECT * FROM attendance_records WHERE day_id=$1 FOR UPDATE',[day.id])).rows;
 for(const record of records) {
  let status,minutes=0;
  if(!state.isSchoolDay)status='not_scheduled';
  else if(record.check_in_at) {
   const arrival=DateTime.fromJSDate(new Date(record.check_in_at));
   status=arrival>state.lateAt?'late':'present';
   if(status==='late')minutes=Math.max(1,Math.floor(arrival.diff(state.start,'minutes').minutes));
  } else status=record.source==='manual'?'absent':state.clock>=state.cutoff?'absent':'pending';
  await db.query('UPDATE attendance_records SET status=$1,late_minutes=$2,updated_at=$3 WHERE id=$4',[status,minutes,now(),record.id]);
 }
 return {attendance_date:day.attendance_date,before,after:schedule};
}
export function recordDto(row) {
 return {...row,external_student_id:row.student_id,session_id:row.day_id,check_in_at:row.check_in_at?new Date(row.check_in_at).toISOString():null};
}
export async function daily(pool,classId,date,now) {
 return transaction(pool,async db=>{
  const day=await ensureDay(db,classId,date,now); const state=dayStatus(day,now);
  const {rows}=await db.query('SELECT * FROM attendance_records WHERE day_id=$1 ORDER BY student_name,student_id',[day.id]);
  return {session_id:day.id,attendance_date:day.attendance_date,timezone:day.timezone,schedule:day.schedule,is_school_day:state.isSchoolDay,
   roll_call_started_at:state.start.toUTC().toISO(),roll_call_completed_at:state.clock>=state.cutoff?state.cutoff.toUTC().toISO():null,records:rows.map(recordDto)};
 });
}
export async function mark(pool,classId,studentId,present,now,actor,confidence=null,source='manual',expectedDayId=null) {
 return transaction(pool,async db=>{
  const day=await ensureDay(db,classId,null,now); const state=dayStatus(day,now);
  if(expectedDayId && day.id!==expectedDayId) fail(409,'انتهى يوم الحضور؛ ابدأ جلسة جديدة');
  const student=await one(db,'SELECT * FROM students WHERE id=$1 AND class_id=$2 AND is_active=true',[studentId,classId],'الطالب غير مسجل في هذا الفصل');
  if(!state.isSchoolDay) fail(409,'اليوم ليس من أيام الدراسة');
  if(present && (state.clock<state.start || state.clock>state.end)) fail(409,'التسجيل خارج مواعيد حضور الفصل');
  const record=await one(db,'SELECT * FROM attendance_records WHERE day_id=$1 AND student_id=$2 FOR UPDATE',[day.id,student.id]);
  // Repeat detections/check-ins must never move the first arrival or change its status.
  if(present && ['present','late'].includes(record.status)) return recordDto(record);
  const late=present && state.clock>state.lateAt;
  const status=present?(late?'late':'present'):'absent';
  const minutes=late?Math.max(1,Math.floor(state.clock.diff(state.start,'minutes').minutes)):0;
  const updated=await one(db,'UPDATE attendance_records SET status=$1,check_in_at=$2,late_minutes=$3,source=$4,recognition_confidence=$5,updated_at=$6 WHERE id=$7 RETURNING *',[status,present?now():null,minutes,source,confidence,now(),record.id]);
  await db.query('INSERT INTO audit_log(actor,action,entity_id,details) VALUES($1,$2,$3,$4)',[actor,'attendance.'+source,record.id,JSON.stringify({before:record.status,after:status,student_id:studentId,day_id:day.id})]);
  return recordDto(updated);
 });
}
