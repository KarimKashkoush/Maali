import { existsSync, mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';

// Development only. Never initialize, replace, stop, or reconfigure a database.
const dataDirectory = process.env.LOCAL_PGDATA;
if (!dataDirectory || process.env.NODE_ENV === 'production') process.exit(0);
if (process.platform !== 'win32') {
  console.log('Start your local PostgreSQL service before running the API.');
  process.exit(0);
}
let database;
try { database = new URL(process.env.DATABASE_URL); }
catch { console.error('DATABASE_URL is missing or invalid. Check the backend .env.'); process.exit(1); }
if (!['postgres:', 'postgresql:'].includes(database.protocol) ||
    !['localhost', '127.0.0.1'].includes(database.hostname)) process.exit(0);

const port = database.port || '5432';
const binaryDirectory = process.env.POSTGRES_BIN || 'C:\\Program Files\\PostgreSQL\\18\\bin';
const readyExecutable = join(binaryDirectory, 'pg_isready.exe');
const controlExecutable = join(binaryDirectory, 'pg_ctl.exe');
for (const executable of [readyExecutable, controlExecutable]) {
  if (!existsSync(executable)) {
    console.error('PostgreSQL tools not found. Set POSTGRES_BIN in the backend .env.');
    process.exit(1);
  }
}
function run(executable, args) {
  const result = spawnSync(executable, args, { windowsHide: true, encoding: 'utf8', timeout: 45000 });
  if (result.error) throw new Error('Cannot run PostgreSQL tools. Check file permissions and POSTGRES_BIN.');
  return result;
}
function isReady() {
  return run(readyExecutable, ['-h', '127.0.0.1', '-p', port, '-q', '-t', '3']).status === 0;
}
try {
  if (isReady()) {
    console.log(`PostgreSQL is ready on 127.0.0.1:${port}.`);
    process.exit(0);
  }
  const dataPath = resolve(dataDirectory);
  if (!existsSync(join(dataPath, 'PG_VERSION'))) {
    throw new Error('LOCAL_PGDATA does not point to an existing PostgreSQL cluster. No database was created.');
  }
  if (run(controlExecutable, ['-D', dataPath, 'status']).status === 0) {
    throw new Error('The configured PostgreSQL cluster is running but is not ready at DATABASE_URL. Check its port and logs.');
  }
  const logDirectory = resolve('.local');
  mkdirSync(logDirectory, { recursive: true });
  console.log(`Starting the existing local PostgreSQL cluster on port ${port}...`);
  const result = run(controlExecutable, ['-D', dataPath, '-l', join(logDirectory, 'postgres.log'), '-o', `-p ${port} -h 127.0.0.1`, '-w', '-t', '30', 'start']);
  // Another terminal may have started the same cluster while this one waited.
  if (!isReady()) {
    if (result.stderr) console.error(result.stderr.trim());
    throw new Error('PostgreSQL did not become ready. Check .local/postgres.log.');
  }
  console.log(`PostgreSQL is ready on 127.0.0.1:${port}.`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
