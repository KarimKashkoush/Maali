import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import pg from 'pg';
export async function migrate(pool) {
  const db = await pool.connect();
  try {
    await db.query('BEGIN');
    await db.query('SELECT pg_advisory_xact_lock(74621938)');
    await db.query('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())');
    const dir = new URL('../migrations/', import.meta.url);
    for (const name of (await readdir(dir)).filter(n => n.endsWith('.sql')).sort()) {
      if ((await db.query('SELECT 1 FROM schema_migrations WHERE name=$1',[name])).rowCount) continue;
      await db.query(await readFile(new URL(name,dir),'utf8'));
      await db.query('INSERT INTO schema_migrations(name) VALUES($1)',[name]);
    }
    await db.query('COMMIT');
  } catch (error) { await db.query('ROLLBACK'); throw error; }
  finally { db.release(); }
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const pool = new pg.Pool({connectionString:process.env.DATABASE_URL});
  try { await migrate(pool); console.log('Migrations applied'); } finally { await pool.end(); }
}
