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
  if (!config.databaseUrl || !config.adminPassword || (process.env.NODE_ENV !== 'development' && config.adminPassword.length < 12) || !config.sessionSecret || config.sessionSecret.length < 32 || !config.recognitionKey) {
    throw new Error('Set DATABASE_URL, ADMIN_PASSWORD (12+ chars outside local development), SESSION_SECRET (32+ chars), RECOGNITION_API_KEY in .env');
  }
  if (!['local', 'supabase'].includes(config.storageProvider)) throw new Error('Invalid STORAGE_PROVIDER');
  if (config.storageProvider === 'supabase' && (!config.supabaseUrl || !config.supabaseKey)) throw new Error('Supabase storage credentials are required');
  if (production && config.storageProvider !== 'supabase') throw new Error('Production requires durable Supabase storage');
  return config;
}
