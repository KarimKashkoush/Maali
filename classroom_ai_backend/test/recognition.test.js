import assert from 'node:assert/strict';
import { test } from 'node:test';
import { recognitionClient } from '../src/recognition.js';

test('recognition readiness accepts a healthy service', async (t) => {
 t.mock.method(globalThis, 'fetch', async (url, init) => {
  assert.equal(url, 'http://127.0.0.1:8001/health');
  assert.ok(init.signal instanceof AbortSignal);
  return Response.json({status:'ok', model:'dlib-v1'});
 });
 await recognitionClient({recognitionUrl:'http://127.0.0.1:8001'}).ready();
});

test('recognition readiness reports unavailable, invalid and failed health responses', async (t) => {
 const mocked = t.mock.method(globalThis, 'fetch');
 for (const result of [null, {status:'ok'}, {status:'failed',model:'dlib-v1'}, 'invalid-json', 503]) {
  mocked.mock.mockImplementation(async () => {
   if (result === null) throw new TypeError('fetch failed');
   if (result === 'invalid-json') return new Response('not json');
   if (result === 503) return Response.json({status:'ok',model:'dlib-v1'}, {status:503});
   return Response.json(result);
  });
  await assert.rejects(recognitionClient({recognitionUrl:'http://127.0.0.1:8001'}).ready(), error => error.status === 503 && error.message.includes('Python'));
 }
});
