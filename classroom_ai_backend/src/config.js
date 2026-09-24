import 'dotenv/config';
export function loadConfig() {
  const production = process.env.NODE_ENV === 'production';
  const config = {
    port: Number(process.env.PORT || 4000),
    databaseUrl: process.env.DATABASE_URL,
    adminUsername: process.env.ADMIN_USERNAME || 'admin',
    adminPassword: process.env.ADMIN_PASSWORD,
    sessionSecret: process.env.SESSION_SECRET,
    secureCookies: production,
    storageProvider: process.env.STORAGE_PROVIDER || 'local',
    storageDir: process.env.UPLOAD_DIR || './uploads',
    supabaseUrl: process.env.SUPABASE_URL,
    supabaseKey: process.env.SUPABASE_SERVICE_ROLE_KEY,
    storageBucket: process.env.STORAGE_BUCKET || 'student-images',
    recognitionUrl: process.env.RECOGNITION_URL || 'http://127.0.0.1:8001',
    recognitionKey: process.env.RECOGNITION_API_KEY,
    recognitionConfirmFrames: 3,
    maxImageBytes: 5 * 1024 * 1024,
  };
  const issues = [];
  if (!config.databaseUrl?.trim()) issues.push('DATABASE_URL is missing');
  if (!config.adminPassword?.trim()) issues.push('ADMIN_PASSWORD is missing');
  else if (process.env.NODE_ENV !== 'development' && config.adminPassword.length < 12) issues.push('ADMIN_PASSWORD requires at least 12 characters');
  if (!config.sessionSecret?.trim()) issues.push('SESSION_SECRET is missing');
  else if (config.sessionSecret.length < 32) issues.push('SESSION_SECRET requires at least 32 characters');
  if (!config.recognitionKey?.trim()) issues.push('RECOGNITION_API_KEY is missing');
  if (config.storageProvider === 'supabase') {
    if (!config.supabaseUrl?.trim()) issues.push('SUPABASE_URL is missing');
    if (!config.supabaseKey?.trim()) issues.push('SUPABASE_SERVICE_ROLE_KEY is missing');
  }
  if (issues.length) throw new Error('Invalid server environment: ' + issues.join('; ') + '. Set these in the hosting service Environment settings.');
  if (!['local', 'supabase'].includes(config.storageProvider)) throw new Error('Invalid STORAGE_PROVIDER');
  if (config.storageProvider === 'supabase' && (!config.supabaseUrl || !config.supabaseKey)) throw new Error('Supabase storage credentials are required');
  if (production && config.storageProvider !== 'supabase') throw new Error('Production requires durable Supabase storage');
  return config;
}
