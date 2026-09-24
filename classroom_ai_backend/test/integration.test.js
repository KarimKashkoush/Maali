import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import pg from 'pg';
import sharp from 'sharp';
import { createApp } from '../src/app.js';
import { migrate } from '../src/migrate.js';

// Run against a dedicated real PostgreSQL database. This suite never uses a
// database mock and refuses database names that do not end in "_test".
const connectionString = process.env.TEST_DATABASE_URL;
if (!connectionString) {
  throw new Error('Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test');
}
if (!new URL(connectionString).pathname.endsWith('_test')) {
  throw new Error('Integration tests require a database name ending in _test');
}

const ADMIN_PASSWORD = 'integration-admin-password-2026';
const INITIAL_TIME = '2026-09-23T04:30:00.000Z'; // Wednesday 07:30 in Riyadh.
const RUN_ID = randomUUID().slice(0, 8);
let pool;
let server;
let baseUrl;
let storageDir;
let cookie;
let image;
let currentTime;
let detections;
let enrollmentFailure;
let lastCandidates;
let recognitionGate;
let readinessFailure;
let sequence = 0;

function at(instant) {
  currentTime = new Date(instant);
}

async function request(path, { method = 'GET', body, authenticated = true, headers = {} } = {}) {
  const init = { method, headers: { ...headers } };
  if (authenticated && cookie) init.headers.Cookie = cookie;
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const response = await fetch(`${baseUrl}${path}`, init);
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json')
    ? await response.json()
    : Buffer.from(await response.arrayBuffer());
  return { status: response.status, headers: response.headers, data };
}

function succeeds(result, context = 'Request') {
  assert.ok(result.status >= 200 && result.status < 300,
    `${context}: expected 2xx, received ${result.status}: ${JSON.stringify(result.data)}`);
  return result.data;
}

function rejected(result, expected = [400, 409, 422]) {
  assert.ok(expected.includes(result.status),
    `Expected ${expected.join('/')} but received ${result.status}: ${JSON.stringify(result.data)}`);
  assert.equal(typeof result.data.detail, 'string', 'API errors should provide a useful detail');
}

async function createClassroom(overrides = {}) {
  const school = succeeds(await request('/schools', {
    method: 'POST', body: { name: `School ${RUN_ID}-${++sequence}`, timezone: 'Asia/Riyadh', ...overrides.school },
  }));
  const stage = succeeds(await request('/stages', {
    method: 'POST', body: { school_id: school.id, name: 'Primary' },
  }));
  const classroom = succeeds(await request('/classrooms', {
    method: 'POST',
    body: {
      school_id: school.id, stage_id: stage.id, classroom_name: `Class ${sequence}`,
      attendance_start: '08:00', grace_minutes: 10, absence_after_minutes: 30,
      attendance_end: '14:00', weekdays: [0, 1, 2, 3, 4], ...overrides.classroom,
    },
  }));
  return { school, stage, classroom };
}

function studentForm(classId, { photo = image, name = `Student ${++sequence}`, mime = 'image/jpeg' } = {}) {
  const body = new FormData();
  body.set('full_name', name);
  body.set('class_id', String(classId));
  if (photo !== null) body.set('photo', new Blob([photo], { type: mime }), 'student.jpg');
  return body;
}

async function createStudent(classId, options) {
  return succeeds(await request('/students', { method: 'POST', body: studentForm(classId, options) }), 'Create student');
}

async function daily(classId, date) {
  return succeeds(await request(`/attendance/daily/class/${classId}${date ? `?date=${date}` : ''}`), 'Daily attendance');
}

function recordFor(day, studentId) {
  assert.ok(Array.isArray(day.records), 'Daily response must contain records');
  const matches = day.records.filter(record => Number(record.student_id ?? record.external_student_id) === Number(studentId));
  assert.equal(matches.length, 1, `Expected exactly one attendance record for student ${studentId}`);
  return matches[0];
}

async function markPresent(classId, studentId) {
  return request(`/attendance/daily/class/${classId}/students/${studentId}`, { method: 'PATCH', body: { present: true } });
}

async function frame(sessionId) {
  const body = new FormData();
  body.set('frame', new Blob([image], { type: 'image/jpeg' }), 'frame.jpg');
  return request(`/attendance/live/frame/${sessionId}`, { method: 'POST', body });
}

describe('Node API with PostgreSQL, HTTP, and private local image storage', { concurrency: false, timeout: 120_000 }, () => {
  before(async () => {
    pool = new pg.Pool({ connectionString, max: 12 });
    await migrate(pool);
    // The migration must be safe to invoke twice at service startup.
    await migrate(pool);
    // Only the explicitly guarded, dedicated _test database is cleared. Keep
    // migrations so repeated suite runs also exercise already-migrated startup.
    await pool.query(`TRUNCATE TABLE classroom_schedule_versions, attendance_records,
      attendance_days, student_images, student_enrollments, students, classrooms,
      stages, schools, audit_log, auth_sessions RESTART IDENTITY`);
    storageDir = await mkdtemp(join(tmpdir(), 'classroom-api-integration-'));
    image = await sharp({ create: { width: 240, height: 240, channels: 3, background: { r: 150, g: 120, b: 90 } } })
      .jpeg().toBuffer();
    at(INITIAL_TIME);
    detections = [];
    const config = {
      adminUsername: 'admin', adminPassword: ADMIN_PASSWORD, sessionSecret: 's'.repeat(64),
      secureCookies: false, storageDir, storageProvider: 'local', maxImageBytes: 5 * 1024 * 1024,
      recognitionConfirmFrames: 3,
    };
    // Only the external vision computation is deterministic here. Image decoding,
    // authentication, SQL transactions, storage, schedules, and HTTP run for real.
    const recognition = {
      ready: async () => { if (readinessFailure) throw readinessFailure; },
      enroll: async () => {
        if (enrollmentFailure) throw enrollmentFailure;
        return { embedding: Array(128).fill(0.1), model: 'dlib-v1' };
      },
      recognize: async (_frame, candidates) => {
        lastCandidates = structuredClone(candidates);
        if (recognitionGate) await recognitionGate();
        return { frame_width: 240, frame_height: 240, detections: structuredClone(detections) };
      },
    };
    const app = createApp({ pool, config, recognition, now: () => new Date(currentTime) });
    server = app.listen(0, '127.0.0.1');
    await once(server, 'listening');
    baseUrl = `http://127.0.0.1:${server.address().port}/api/v1`;
    const login = await request('/auth/login', {
      method: 'POST', authenticated: false, body: { username: 'admin', password: ADMIN_PASSWORD },
    });
    succeeds(login, 'Login');
    const setCookie = login.headers.get('set-cookie');
    assert.ok(setCookie, 'Login must set an HTTP-only session cookie');
    assert.match(setCookie, /HttpOnly/i);
    assert.match(setCookie, /SameSite=(Lax|Strict)/i);
    cookie = setCookie.split(';')[0];
  });

  beforeEach(() => {
    at(INITIAL_TIME);
    detections = [];
    enrollmentFailure = null;
    readinessFailure = null;
    lastCandidates = null;
    recognitionGate = null;
  });

  after(async () => {
    if (server) await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    if (pool) await pool.end();
    if (storageDir) {
      assert.equal(dirname(resolve(storageDir)), resolve(tmpdir()));
      assert.ok(basename(storageDir).startsWith('classroom-api-integration-'));
      await rm(storageDir, { recursive: true, force: true });
    }
  });

  test('preserves school classification and keeps each stage classrooms separate', async () => {
    const { school, stage, classroom } = await createClassroom({school: {school_type:'girls', curriculum:'international'}});
    assert.equal(school.school_type, 'girls');
    assert.equal(school.curriculum, 'international');
    const second = succeeds(await request('/stages', {method:'POST', body:{school_id:school.id, name:'Secondary'}}));
    const other = succeeds(await request('/classrooms', {method:'POST', body:{school_id:school.id, stage_id:second.id, classroom_name:'Secondary class'}}));
    const changed = succeeds(await request('/schools/' + school.id, {method:'PATCH', body:{name:school.name + ' updated'}}));
    assert.equal(changed.school_type, 'girls');
    assert.equal(changed.curriculum, 'international');
    const listed = succeeds(await request('/schools')).find(s => s.id === school.id);
    assert.deepEqual(listed.stage.find(s => s.id === stage.id).classrooms.map(c => c.id), [classroom.id]);
    assert.deepEqual(listed.stage.find(s => s.id === second.id).classrooms.map(c => c.id), [other.id]);
    rejected(await request('/schools/' + school.id, {method:'PATCH',body:{curriculum:'invalid'}}), [422]);
    const updated = succeeds(await request('/schools/' + school.id, {method:'PATCH',body:{school_type:'kindergarten',curriculum:'national'}}));
    assert.equal(updated.school_type, 'kindergarten');
    assert.equal(updated.curriculum, 'national');
  });

  test('requires authenticated access and rejects a tampered session', async () => {
    assert.equal((await request('/schools', { authenticated: false })).status, 401);
    assert.equal((await request('/students', { authenticated: false })).status, 401);
    assert.equal((await request('/schools', { authenticated: false, headers: { Cookie: `${cookie}tampered` } })).status, 401);
    const invalid = await request('/auth/login', {
      method: 'POST', authenticated: false, body: { username: 'admin', password: 'invalid-password' },
    });
    assert.equal(invalid.status, 401);
    succeeds(await request('/schools'));
  });

  test('logout revokes the server session while another signed-in session remains valid', async () => {
    const login = await request('/auth/login', {
      method: 'POST', authenticated: false, body: { username: 'admin', password: ADMIN_PASSWORD },
    });
    succeeds(login);
    const secondCookie = login.headers.get('set-cookie').split(';')[0];
    const headers = { Cookie: secondCookie };
    succeeds(await request('/auth/me', { authenticated: false, headers }));
    succeeds(await request('/auth/logout', { method: 'POST', authenticated: false, headers }));
    assert.equal((await request('/auth/me', { authenticated: false, headers })).status, 401);
    succeeds(await request('/auth/me'));
  });

  test('rejects a stage belonging to a different school and invalid schedule settings', async () => {
    const first = await createClassroom();
    const second = await createClassroom();
    const base = {
      school_id: first.school.id, stage_id: first.stage.id, classroom_name: 'Invalid class',
      attendance_start: '08:00', grace_minutes: 10, absence_after_minutes: 30,
      attendance_end: '14:00', weekdays: [0, 1, 2, 3, 4],
    };
    for (const invalid of [
      { stage_id: second.stage.id }, { attendance_end: '07:00' },
      { absence_after_minutes: 5 }, { weekdays: [] }, { weekdays: [8] },
    ]) {
      rejected(await request('/classrooms', { method: 'POST', body: { ...base, ...invalid } }));
    }
    rejected(await request('/schools', { method: 'POST', body: { name: `Bad timezone ${RUN_ID}`, timezone: 'Earth/Unknown' } }));
  });

  test('enrolls without a photo while recognition is offline and supports adding one later', async () => {
    const {classroom}=await createClassroom();
    enrollmentFailure=Object.assign(new Error('offline'),{status:503});
    const student=await createStudent(classroom.id,{photo:null});
    assert.equal(student.photo_url,null);
    assert.deepEqual(student.students_images,[]);
    at('2026-09-23T05:05:00Z');
    succeeds(await markPresent(classroom.id,student.id));
    assert.equal(recordFor(await daily(classroom.id),student.id).status,'present');
    const session=succeeds(await request('/attendance/live/start',{method:'POST',body:{class_id:classroom.id}}));
    assert.equal(session.enrolled_students,0);
    enrollmentFailure=null;
    const body=new FormData();body.set('photo',new Blob([image],{type:'image/jpeg'}),'photo.jpg');body.set('type','primary');
    succeeds(await request('/students/'+student.id+'/images',{method:'POST',body}));
    const restarted=succeeds(await request('/attendance/live/start',{method:'POST',body:{class_id:classroom.id}}));
    assert.equal(restarted.enrolled_students,1);
  });

  test('validates an attached photo and rolls back failed recognition enrollment', async () => {
    const { classroom } = await createClassroom();

    rejected(await request('/students', { method: 'POST', body: studentForm(classroom.id, { photo: Buffer.from('not a photograph') }) }));
    enrollmentFailure = Object.assign(new Error('Exactly one face is required'), { status: 422 });
    rejected(await request('/students', { method: 'POST', body: studentForm(classroom.id) }), [422]);
    enrollmentFailure = Object.assign(new Error('Recognition service is unavailable'), { status: 503 });
    rejected(await request('/students', { method: 'POST', body: studentForm(classroom.id) }), [503]);
    const count = await pool.query('SELECT count(*)::int AS count FROM students WHERE class_id=$1', [classroom.id]);
    assert.equal(count.rows[0].count, 0, 'An unusable photo must not leave a partially enrolled student');
    enrollmentFailure = null;
    const student = await createStudent(classroom.id);
    assert.equal(Number(student.class_id), classroom.id);
  });

  test('stores the required photo privately and never exposes a face embedding in student JSON', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    const detail = succeeds(await request(`/students/${student.id}`));
    assert.equal(detail.students_images.length, 1);
    assert.ok(detail.students_images[0].image_url);
    assert.equal(JSON.stringify(detail).includes('embedding'), false);
    const privateUrl = `${baseUrl}/images/${detail.students_images[0].id}/content`;
    const anonymous = await fetch(privateUrl);
    assert.equal(anonymous.status, 401, 'Student photos require the administrator session');
    await anonymous.arrayBuffer();
    const authorized = await fetch(privateUrl, { headers: { Cookie: cookie } });
    assert.equal(authorized.status, 200);
    assert.match(authorized.headers.get('content-type'), /^image\//);
    const stored = Buffer.from(await authorized.arrayBuffer());
    assert.equal((await sharp(stored).metadata()).format, 'jpeg');
  });

  test('refuses to delete the last photo, including competing deletion requests', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    const first = succeeds(await request(`/students/${student.id}`)).students_images[0];
    rejected(await request(`/students/${student.id}/images/${first.id}`, { method: 'DELETE' }), [400, 409, 422]);
    const body = new FormData();
    body.set('type', 'front');
    body.set('photo', new Blob([image], { type: 'image/jpeg' }), 'front.jpg');
    succeeds(await request(`/students/${student.id}/images`, { method: 'POST', body }));
    const photos = succeeds(await request(`/students/${student.id}`)).students_images;
    assert.equal(photos.length, 2);
    const deletions = await Promise.all(photos.map(photo => request(`/students/${student.id}/images/${photo.id}`, { method: 'DELETE' })));
    assert.equal(deletions.filter(result => result.status >= 200 && result.status < 300).length, 1);
    rejected(deletions.find(result => result.status >= 400), [400, 409, 422]);
    assert.equal(succeeds(await request(`/students/${student.id}`)).students_images.length, 1);
  });

  test('keeps students pending until the exact absence cutoff', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-23T05:29:59.999Z');
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending');
    at('2026-09-23T05:30:00.000Z');
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'absent');
  });

  test('uses the grace boundary consistently and lets an absent student arrive late', async () => {
    const { classroom } = await createClassroom();
    const onTime = await createStudent(classroom.id);
    const late = await createStudent(classroom.id);
    const arrivesAfterCutoff = await createStudent(classroom.id);
    at('2026-09-23T05:10:00.000Z');
    succeeds(await markPresent(classroom.id, onTime.id));
    assert.equal(recordFor(await daily(classroom.id), onTime.id).status, 'present');
    at('2026-09-23T05:10:00.001Z');
    succeeds(await markPresent(classroom.id, late.id));
    const lateRecord = recordFor(await daily(classroom.id), late.id);
    assert.equal(lateRecord.status, 'late');
    assert.ok(lateRecord.late_minutes > 0);
    at('2026-09-23T06:00:00.000Z');
    assert.equal(recordFor(await daily(classroom.id), arrivesAfterCutoff.id).status, 'absent');
    succeeds(await markPresent(classroom.id, arrivesAfterCutoff.id));
    assert.equal(recordFor(await daily(classroom.id), arrivesAfterCutoff.id).status, 'late');
    assert.equal(recordFor(await daily(classroom.id), onTime.id).status, 'present');
  });

  test('uses the school timezone at midnight and isolates consecutive local dates', async () => {
    const { classroom } = await createClassroom({
      classroom: { attendance_start: '00:00', attendance_end: '05:00', weekdays: [0, 1, 2, 3, 4, 5, 6] },
    });
    const student = await createStudent(classroom.id);
    at('2026-09-22T21:05:00.000Z'); // Wednesday 00:05 locally, Tuesday in UTC.
    succeeds(await markPresent(classroom.id, student.id));
    assert.equal(recordFor(await daily(classroom.id, '2026-09-23'), student.id).status, 'present');
    at('2026-09-23T21:05:00.000Z'); // Thursday 00:05 locally.
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending');
    assert.equal(recordFor(await daily(classroom.id, '2026-09-23'), student.id).status, 'present');
    const days = await pool.query('SELECT attendance_date::text FROM attendance_days WHERE class_id=$1 ORDER BY attendance_date', [classroom.id]);
    assert.deepEqual(days.rows.map(row => row.attendance_date), ['2026-09-23', '2026-09-24']);
  });

  test('does not mark students absent on an unscheduled day', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-25T08:00:00.000Z'); // Friday.
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'not_scheduled');
    rejected(await markPresent(classroom.id, student.id), [400, 409, 422]);
  });

  test('rejects arrival outside the configured attendance window', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-23T04:59:59.999Z');
    rejected(await markPresent(classroom.id, student.id), [400, 409, 422]);
    at('2026-09-23T11:00:00.001Z');
    rejected(await markPresent(classroom.id, student.id), [400, 409, 422]);
    assert.equal(recordFor(await daily(classroom.id), student.id).check_in_at, null);
  });

  test('applies schedules today, recalculates derived attendance and preserves arrival times and manual absence', async () => {
    const {classroom}=await createClassroom();
    const arrived=await createStudent(classroom.id);
    const missing=await createStudent(classroom.id);
    const manual=await createStudent(classroom.id);
    at('2026-09-23T05:20:00Z');
    succeeds(await markPresent(classroom.id,arrived.id));
    succeeds(await request('/attendance/daily/class/'+classroom.id+'/students/'+manual.id,{method:'PATCH',body:{present:false}}));
    at('2026-09-23T05:40:00Z');
    const before=await daily(classroom.id);
    assert.equal(recordFor(before,arrived.id).status,'late');
    assert.equal(recordFor(before,missing.id).status,'absent');
    succeeds(await request('/classrooms/'+classroom.id,{method:'PATCH',body:{attendance_start:'09:00'}}));
    succeeds(await request('/classrooms/'+classroom.id,{method:'PATCH',body:{attendance_start:'08:30',schedule_effective:'today'}}));
    const after=await daily(classroom.id);
    assert.equal(after.schedule.attendance_start.slice(0,5),'08:30');
    assert.equal(recordFor(after,arrived.id).status,'present');
    assert.equal(recordFor(after,arrived.id).check_in_at,recordFor(before,arrived.id).check_in_at);
    assert.equal(recordFor(after,missing.id).status,'pending');
    assert.equal(recordFor(after,manual.id).status,'absent');
    at('2026-09-24T05:40:00Z');
    assert.equal((await daily(classroom.id)).schedule.attendance_start.slice(0,5),'08:30');
    succeeds(await request('/classrooms/'+classroom.id,{method:'PATCH',body:{attendance_start:'07:00',schedule_effective:'today'}}));
    assert.equal((await daily(classroom.id,'2026-09-23')).schedule.attendance_start.slice(0,5),'08:30');
    rejected(await request('/classrooms/'+classroom.id,{method:'PATCH',body:{schedule_effective:'yesterday'}}),[422]);
  });

  test('preserves the current day schedule while applying schedule changes to the next day', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    await daily(classroom.id);
    succeeds(await request(`/classrooms/${classroom.id}`, { method: 'PATCH', body: { grace_minutes: 20 } }));
    at('2026-09-23T05:15:00.000Z');
    succeeds(await markPresent(classroom.id, student.id));
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'late');
    at('2026-09-24T05:15:00.000Z');
    succeeds(await markPresent(classroom.id, student.id));
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'present');
  });

  test('keeps historical weekdays and timezone even when their attendance day was never opened', async () => {
    const { school, classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    const unopened = await pool.query('SELECT count(*)::int AS count FROM attendance_days WHERE class_id=$1', [classroom.id]);
    assert.equal(unopened.rows[0].count, 0);
    at('2026-09-24T05:00:00.000Z');
    succeeds(await request(`/classrooms/${classroom.id}`, { method: 'PATCH', body: { weekdays: [5] } }));
    succeeds(await request(`/schools/${school.id}`, { method: 'PATCH', body: { timezone: 'Asia/Dubai' } }));
    const wednesday = await daily(classroom.id, '2026-09-23');
    assert.equal(wednesday.timezone, 'Asia/Riyadh');
    assert.equal(wednesday.is_school_day, true);
    assert.deepEqual(wednesday.schedule.weekdays, [0, 1, 2, 3, 4]);
    assert.equal(recordFor(wednesday, student.id).status, 'absent');
    at('2026-09-25T05:00:00.000Z');
    const friday = await daily(classroom.id);
    assert.equal(friday.timezone, 'Asia/Dubai');
    assert.equal(friday.is_school_day, true);
    assert.deepEqual(friday.schedule.weekdays, [5]);
  });

  test('handles concurrent check-ins once and preserves the first arrival time', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-23T05:05:00.000Z');
    const responses = await Promise.all(Array.from({ length: 8 }, () => markPresent(classroom.id, student.id)));
    responses.forEach(response => succeeds(response));
    const first = recordFor(await daily(classroom.id), student.id);
    assert.equal(first.status, 'present');
    assert.equal(new Date(first.check_in_at).toISOString(), '2026-09-23T05:05:00.000Z');
    at('2026-09-23T07:00:00.000Z');
    succeeds(await markPresent(classroom.id, student.id));
    const repeated = recordFor(await daily(classroom.id), student.id);
    assert.equal(repeated.status, 'present');
    assert.equal(repeated.check_in_at, first.check_in_at);
    const records = await pool.query('SELECT count(*)::int AS count FROM attendance_records WHERE student_id=$1', [student.id]);
    assert.equal(records.rows[0].count, 1);
  });

  test('preserves attendance history after a student moves to another classroom', async () => {
    const old = await createClassroom();
    const destination = await createClassroom();
    const student = await createStudent(old.classroom.id);
    at('2026-09-23T05:05:00.000Z');
    succeeds(await markPresent(old.classroom.id, student.id));
    at('2026-09-24T04:30:00.000Z');
    succeeds(await request(`/students/${student.id}`, {
      method: 'PATCH', body: { class_id: destination.classroom.id },
    }));
    const history = await daily(old.classroom.id, '2026-09-23');
    assert.equal(recordFor(history, student.id).status, 'present');
    assert.equal((await daily(old.classroom.id)).records.some(row => row.student_id === student.id), false);
    assert.equal(recordFor(await daily(destination.classroom.id), student.id).status, 'pending');
    rejected(await markPresent(old.classroom.id, student.id), [400, 404, 409, 422]);
  });

  test('deactivates and reactivates a student on the same day without losing enrollment history', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-23T05:05:00.000Z');
    succeeds(await markPresent(classroom.id, student.id));
    const previousArrival = recordFor(await daily(classroom.id), student.id).check_in_at;
    at('2026-09-24T04:30:00.000Z');
    succeeds(await request(`/students/${student.id}`, { method: 'PATCH', body: { is_active: false } }));
    const active = succeeds(await request(`/students?class_id=${classroom.id}`));
    assert.equal(active.some(row => row.id === student.id), false);
    const management = succeeds(await request(`/students?class_id=${classroom.id}&include_inactive=true`));
    assert.equal(management.find(row => row.id === student.id)?.is_active, false);
    const inactiveRoster = succeeds(await request(`/classrooms/${classroom.id}`));
    assert.equal(inactiveRoster.students.some(row => row.id === student.id), false);
    assert.equal((await daily(classroom.id)).records.some(row => row.student_id === student.id), false);
    const historical = recordFor(await daily(classroom.id, '2026-09-23'), student.id);
    assert.equal(historical.status, 'present');
    assert.equal(historical.check_in_at, previousArrival);
    rejected(await markPresent(classroom.id, student.id), [404]);
    succeeds(await request(`/students/${student.id}`, { method: 'PATCH', body: { is_active: true } }));
    const restored = succeeds(await request(`/students?class_id=${classroom.id}`));
    assert.equal(restored.find(row => row.id === student.id)?.is_active, true);
    const restoredRoster = succeeds(await request(`/classrooms/${classroom.id}`));
    assert.equal(restoredRoster.students.filter(row => row.id === student.id).length, 1);
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending');
    const enrollment = await pool.query('SELECT count(*)::int AS count FROM student_enrollments WHERE student_id=$1 AND withdrawn_on IS NULL', [student.id]);
    assert.equal(enrollment.rows[0].count, 1);
    at('2026-09-24T05:05:00.000Z');
    succeeds(await markPresent(classroom.id, student.id));
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'present');
    assert.equal(recordFor(await daily(classroom.id, '2026-09-23'), student.id).check_in_at, previousArrival);
  });

  test('rejects malformed identifiers and impossible attendance dates without server errors', async () => {
    const { classroom } = await createClassroom();
    for (const path of ['/students/not-a-number', '/classrooms/-1', '/schools/1.5', `/attendance/daily/class/${classroom.id}?date=2026-02-30`]) {
      rejected(await request(path), [400, 404, 422]);
    }
  });

  test('does not activate a camera session while recognition is unavailable and recovers after restart', async () => {
    const { classroom } = await createClassroom();
    await createStudent(classroom.id);
    at('2026-09-23T05:05:00.000Z');
    readinessFailure = Object.assign(new Error('Start Python recognition service'), {status: 503});
    rejected(await request('/attendance/live/start', {method: 'POST', body: {class_id: classroom.id}}), [503]);
    const day = await daily(classroom.id);
    rejected(await frame(day.session_id), [409]);
    readinessFailure = null;
    const session = succeeds(await request('/attendance/live/start', {method: 'POST', body: {class_id: classroom.id}}));
    succeeds(await frame(session.session_id));
    succeeds(await request(`/attendance/live/stop/${session.session_id}`, {method: 'POST'}));
  });

  test('reuses one live session for concurrent start requests and stops it cleanly', async () => {
    const { classroom } = await createClassroom();
    await createStudent(classroom.id);
    at('2026-09-23T05:05:00.000Z');
    const starts = await Promise.all(Array.from({ length: 6 }, () => request('/attendance/live/start', {
      method: 'POST', body: { class_id: classroom.id, camera_mode: 'browser' },
    })));
    const sessions = starts.map(result => succeeds(result));
    assert.equal(new Set(sessions.map(session => session.session_id)).size, 1);
    assert.equal(sessions[0].enrolled_students, 1);
    const sessionId = sessions[0].session_id;
    succeeds(await request(`/attendance/live/stop/${sessionId}`, { method: 'POST' }));
    rejected(await frame(sessionId), [409]);
  });

  test('discards an in-flight frame from a stopped session even when the same day is restarted', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-23T05:05:00.000Z');
    const session = succeeds(await request('/attendance/live/start', { method: 'POST', body: { class_id: classroom.id } }));
    detections = [{ top: 10, right: 200, bottom: 210, left: 20, matched: true, student_id: student.id, confidence: 0.95, distance: 0.2 }];
    succeeds(await frame(session.session_id));
    succeeds(await frame(session.session_id));
    let signalEntered;
    let release;
    const entered = new Promise(resolve => { signalEntered = resolve; });
    const blocked = new Promise(resolve => { release = resolve; });
    recognitionGate = async () => { signalEntered(); await blocked; };
    const oldFrame = frame(session.session_id);
    try {
      await Promise.race([entered, oldFrame.then(() => { throw new Error('Frame returned before the recognition gate'); })]);
      succeeds(await request(`/attendance/live/stop/${session.session_id}`, { method: 'POST' }));
      const restarted = succeeds(await request('/attendance/live/start', { method: 'POST', body: { class_id: classroom.id } }));
      assert.equal(restarted.session_id, session.session_id);
      release();
      rejected(await oldFrame, [409]);
      assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending');
      recognitionGate = null;
      succeeds(await frame(restarted.session_id));
      succeeds(await frame(restarted.session_id));
      assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending');
      succeeds(await frame(restarted.session_id));
      assert.equal(recordFor(await daily(classroom.id), student.id).status, 'present');
    } finally {
      release();
      recognitionGate = null;
      await oldFrame;
    }
  });

  test('requires three consecutive recognized frames and preserves the first automatic arrival', async () => {
    const { classroom } = await createClassroom();
    const student = await createStudent(classroom.id);
    at('2026-09-23T05:05:00.000Z');
    const session = succeeds(await request('/attendance/live/start', { method: 'POST', body: { class_id: classroom.id } }));
    const match = { top: 10, right: 200, bottom: 210, left: 20, matched: true, student_id: student.id, confidence: 0.95, distance: 0.2 };
    detections = [match];
    succeeds(await frame(session.session_id));
    succeeds(await frame(session.session_id));
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending');
    detections = [{ ...match, matched: false, student_id: null, confidence: 0, distance: null }];
    succeeds(await frame(session.session_id));
    detections = [match];
    succeeds(await frame(session.session_id));
    succeeds(await frame(session.session_id));
    assert.equal(recordFor(await daily(classroom.id), student.id).status, 'pending', 'An unknown frame must reset confirmation');
    succeeds(await frame(session.session_id));
    const arrived = recordFor(await daily(classroom.id), student.id);
    assert.equal(arrived.status, 'present');
    assert.equal(arrived.source, 'recognition');
    assert.ok(Math.abs(arrived.recognition_confidence - 0.95) < 0.001);
    assert.deepEqual(lastCandidates.map(candidate => candidate.student_id), [student.id]);
    assert.equal(lastCandidates[0].embeddings[0].length, 128);
    at('2026-09-23T06:00:00.000Z');
    succeeds(await frame(session.session_id));
    const repeated = recordFor(await daily(classroom.id), student.id);
    assert.equal(repeated.status, 'present');
    assert.equal(repeated.check_in_at, arrived.check_in_at);
  });

  test('discards matches outside the selected class and low-confidence recognitions', async () => {
    const first = await createClassroom();
    const second = await createClassroom();
    const student = await createStudent(first.classroom.id);
    const outsider = await createStudent(second.classroom.id);
    at('2026-09-23T05:05:00.000Z');
    const session = succeeds(await request('/attendance/live/start', { method: 'POST', body: { class_id: first.classroom.id } }));
    detections = [
      { top: 0, right: 100, bottom: 120, left: 0, matched: true, student_id: outsider.id, confidence: 0.99, distance: 0.01 },
      { top: 0, right: 230, bottom: 120, left: 130, matched: true, student_id: student.id, confidence: 0.4, distance: 0.6 },
    ];
    for (let index = 0; index < 3; index++) {
      const result = succeeds(await frame(session.session_id));
      assert.ok(result.detections.every(detection => detection.matched === false));
    }
    assert.deepEqual(lastCandidates.map(candidate => candidate.student_id), [student.id]);
    assert.equal(recordFor(await daily(first.classroom.id), student.id).status, 'pending');
    assert.equal(recordFor(await daily(second.classroom.id), outsider.id).status, 'pending');
  });

  test('invalidates an active recognition session when a student moves classes', async () => {
    const old = await createClassroom();
    const destination = await createClassroom();
    const student = await createStudent(old.classroom.id);
    at('2026-09-23T05:05:00.000Z');
    const session = succeeds(await request('/attendance/live/start', { method: 'POST', body: { class_id: old.classroom.id } }));
    succeeds(await request(`/students/${student.id}`, { method: 'PATCH', body: { class_id: destination.classroom.id } }));
    rejected(await frame(session.session_id), [409]);
  });
});
