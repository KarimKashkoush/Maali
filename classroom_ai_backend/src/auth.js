import {createHmac,randomBytes,timingSafeEqual} from 'node:crypto';
import {rateLimit} from 'express-rate-limit';
export function setupAuth(app,pool,config) {
 const hash=value=>createHmac('sha256',config.sessionSecret).update(value).digest('hex');
 const cookie=req=>req.headers.cookie?.split(';').map(x=>x.trim()).find(x=>x.startsWith('classroom_session='))?.slice(18);
 const cookieOptions={httpOnly:true,secure:config.secureCookies,sameSite:'strict',path:'/',maxAge:12*60*60*1000};
 const limiter=rateLimit({windowMs:15*60*1000,limit:15,standardHeaders:'draft-8',legacyHeaders:false,message:{detail:'محاولات دخول كثيرة، حاول لاحقًا'}});
 app.post('/api/v1/auth/login',limiter,async(req,res)=>{
  const user=String(req.body?.username||''); const pass=String(req.body?.password||'');
  if(!timingSafeEqual(Buffer.from(hash(user)),Buffer.from(hash(config.adminUsername))) || !timingSafeEqual(Buffer.from(hash(pass)),Buffer.from(hash(config.adminPassword)))) return res.status(401).json({detail:'اسم المستخدم أو كلمة المرور غير صحيحة'});
  const token=randomBytes(32).toString('hex');
  await pool.query('DELETE FROM auth_sessions WHERE expires_at < now()');
  await pool.query("INSERT INTO auth_sessions(token_hash,username,expires_at) VALUES($1,$2,now()+interval '12 hours')",[hash(token),user]);
  res.cookie('classroom_session',token,cookieOptions).json({username:user});
 });
 app.use('/api/v1',async(req,res,next)=>{
  const token=cookie(req); if(!token || token.length!==64)return res.status(401).json({detail:'سجّل الدخول أولًا'});
  const {rows}=await pool.query('SELECT username FROM auth_sessions WHERE token_hash=$1 AND expires_at>now()',[hash(token)]);
  if(!rows[0])return res.status(401).json({detail:'انتهت جلسة الدخول'});
  req.actor=rows[0].username; next();
 });
 app.get('/api/v1/auth/me',(req,res)=>res.json({username:req.actor}));
 app.post('/api/v1/auth/logout',async(req,res)=>{
  await pool.query('DELETE FROM auth_sessions WHERE token_hash=$1',[hash(cookie(req)||'')]);
  res.clearCookie('classroom_session',{...cookieOptions,maxAge:undefined}).json({ok:true});
 });
}
