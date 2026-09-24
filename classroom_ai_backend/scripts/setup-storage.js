import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { config as loadEnv } from 'dotenv';

const MAX_FILE_BYTES = 5 * 1024 * 1024;

function settings(env) {
  const key = env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!env.SUPABASE_URL || !key || /^(YOUR_|REPLACE_|CHANGE_ME)/i.test(key)) {
    throw new Error('Set SUPABASE_URL and the server-only SUPABASE_SERVICE_ROLE_KEY first.');
  }
  let url;
  try { url = new URL(env.SUPABASE_URL); } catch { throw new Error('SUPABASE_URL must be a valid HTTPS project URL.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('SUPABASE_URL must be an HTTPS project origin without credentials, a path, or query parameters.');
  }
  const bucket = env.STORAGE_BUCKET || 'student-images';
  if (!/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(bucket)) {
    throw new Error('STORAGE_BUCKET must contain 3–63 lowercase letters, numbers, or hyphens.');
  }
  return { origin: url.origin, key, bucket };
}

function verifyBucket(data, bucket) {
  if (!data || data.id !== bucket || data.public !== false) {
    throw new Error('The selected bucket is public or its privacy cannot be verified. No existing bucket was changed. Use a dedicated private bucket.');
  }
  const types = data.allowed_mime_types;
  if (Number(data.file_size_limit) !== MAX_FILE_BYTES || !Array.isArray(types) || types.length !== 1 || types[0] !== 'image/jpeg') {
    throw new Error('The existing private bucket must allow only image/jpeg with a 5242880-byte file limit. No settings were changed; configure a dedicated bucket and retry.');
  }
}

/** Idempotent: never changes or deletes an existing bucket or any image. */
export async function setupStorage({ env = process.env, fetchImpl = fetch } = {}) {
  const { origin, key, bucket } = settings(env);
  const endpoint = `${origin}/storage/v1/bucket`;
  const headers = { Authorization: `Bearer ${key}`, apikey: key, 'Content-Type': 'application/json' };

  async function request(url, options = {}) {
    let response;
    try {
      response = await fetchImpl(url, { ...options, headers, redirect: 'error', signal: AbortSignal.timeout(20_000) });
    } catch {
      // Never print response bodies, request headers, or credentials.
      throw new Error('Supabase Storage could not be reached over HTTPS. Check the project URL, network, and service availability.');
    }
    const data = await response.json().catch(() => null);
    return { response, data };
  }

  const existing = await request(`${endpoint}/${encodeURIComponent(bucket)}`);
  if (existing.response.ok) {
    verifyBucket(existing.data, bucket);
    return { bucket, created: false };
  }
  // Storage sometimes wraps a missing bucket as HTTP 400/statusCode 404.
  const missing = existing.response.status === 404 ||
    (existing.response.status === 400 && String(existing.data?.statusCode) === '404');
  if (!missing) throw new Error(`Could not inspect the storage bucket (HTTP ${existing.response.status}). Check the server key and project access.`);

  const created = await request(endpoint, {
    method: 'POST',
    body: JSON.stringify({ id: bucket, name: bucket, public: false,
      file_size_limit: MAX_FILE_BYTES, allowed_mime_types: ['image/jpeg'] }),
  });
  const raced = created.response.status === 409 ||
    (created.response.status === 400 && String(created.data?.statusCode) === '409');
  if (!created.response.ok && !raced) {
    throw new Error(`Could not create the private bucket (HTTP ${created.response.status}). No existing bucket was changed.`);
  }
  const verified = await request(`${endpoint}/${encodeURIComponent(bucket)}`);
  if (!verified.response.ok) throw new Error(`Could not verify the bucket after creation (HTTP ${verified.response.status}). Retry the setup command.`);
  verifyBucket(verified.data, bucket);
  return { bucket, created: created.response.ok };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  loadEnv({ quiet: true });
  try {
    const result = await setupStorage();
    console.log(`${result.created ? 'Created' : 'Verified'} private bucket '${result.bucket}' (JPEG only, 5 MiB maximum).`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
