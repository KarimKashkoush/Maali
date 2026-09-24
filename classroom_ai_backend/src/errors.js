export function fail(status, detail) { const error = new Error(detail); error.status = status; throw error; }
export async function transaction(pool, fn) {
 const db = await pool.connect();
 try { await db.query('BEGIN'); const result = await fn(db); await db.query('COMMIT'); return result; }
 catch(e) { await db.query('ROLLBACK'); throw e; } finally { db.release(); }
}
export async function one(db,sql,args,detail='غير موجود') {
 const {rows} = await db.query(sql,args); if(!rows[0]) fail(404,detail); return rows[0];
}
