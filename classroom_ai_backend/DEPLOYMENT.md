# النشر التجريبي والنسخ الاحتياطي

هذا الدليل يجهز النشر؛ لا يعني أن الخدمات منشورة بالفعل. الأسعار والحدود التالية تحققت من المصادر الرسمية في 23 سبتمبر 2026، وقد تتغير. ابدأ بتجربة صغيرة ثم قِس سرعة التعرف واستهلاك الذاكرة قبل الاعتماد على بث فصل كامل.

## 1. قاعدة PostgreSQL جديدة

أنشئ مشروع Supabase مستقلًا لهذه النسخة. **لا تشغّل migrations على schema قديم يحتوي جداول المشروع السابق**؛ الكود يطبق migrations عند كل تشغيل، ولا ينقل البيانات القديمة تلقائيًا.

انسخ `.env.example` إلى `.env` فقط في تثبيت جديد، ثم ضع قيمًا فعلية لـ `DATABASE_URL` و`ADMIN_PASSWORD` و`SESSION_SECRET` و`RECOGNITION_API_KEY`. استخدم كلمات مرور وأسرارًا عشوائية مختلفة؛ الحد الأدنى لكلمة مرور المدير 12 حرفًا ولمفتاح الجلسة 32 حرفًا. احتفظ بالأسرار في إعدادات الخادم، خارج Git وخارج `NEXT_PUBLIC_*`.

من نافذة **Connect** في Supabase انسخ الاتصال المباشر إن كانت الاستضافة تدعم IPv6؛ وإلا استخدم **Session pooler** على 5432. لا تخمن اسم مضيف الـ pooler. شفّر رموز كلمة المرور المحجوزة داخل الرابط، واستخدم TLS مع التحقق من الشهادة (`sslmode=verify-full`، ومع `sslrootcert` إذا احتاج المضيف شهادة المشروع). لا تعالج مشكلة الشهادة بتعطيل التحقق. تفاصيل الاختيار في [الاتصال بـ PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres).

مثال شكلي، وليس بيانات اتصال صالحة:

```dotenv
DATABASE_URL=postgresql://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@YOUR_SESSION_POOLER:5432/postgres?sslmode=verify-full
NODE_ENV=production
```

بعد التحقق من أن الوجهة هي المشروع الجديد:

```powershell
npm ci
npm run migrate
```

الاختبارات تحتاج قاعدة أخرى منفصلة ينتهي اسمها بـ `_test`؛ لا تشغّلها على قاعدة Supabase الإنتاجية أو على schema مشتركة معها. أبقِ `TEST_DATABASE_URL` خاصًا ببيئة الاختبار المحلية.

## 2. صور خاصة ودائمة

داخل إعدادات الباك إند فقط:

```dotenv
STORAGE_PROVIDER=supabase
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=SERVER_ONLY_SECRET
STORAGE_BUCKET=student-images
```

شغّل من مجلد الباك إند:

```powershell
node --env-file-if-exists=.env scripts/setup-storage.js
```

السكربت يقرأ bucket المحدد أولًا. إن لم يوجد، ينشئه **private** بحد 5 MiB ونوع `image/jpeg` فقط، ثم يراجع الإعدادات. إن كان موجودًا ومطابقًا يكتفي بالتحقق. يرفض bucket عام أو إعدادات مخالفة، ولا يعدّل bucket موجودًا ولا يحذف محتوياته. عند الرفض اختر bucket مخصصًا جديدًا أو اضبط إعداداته صراحة في Dashboard ثم أعد الأمر.

Node يحول الصور إلى JPEG قبل الرفع، ويستخدم service role key على الخادم فقط. لا تجعل bucket عامًا، ولا تضف سياسة قراءة عامة للصور. الواجهة تطلب الصور عبر جلسة المدير وAPI الباك إند. راجع [إعداد buckets وقيود الرفع](https://supabase.com/docs/guides/storage/buckets/creating-buckets).

## 3. الخدمات وطريقة الربط

الخدمات المطلوبة: Next.js للواجهة، وNode.js API، وPython للتعرف، وSupabase لقاعدة البيانات والتخزين. حافظ على ترتيب إعداد قاعدة البيانات ثم Python ثم Node ثم الواجهة.

- **Python:** ابْنِ `ClassroomAI/recognition_service/Dockerfile` باستخدام مجلد `ClassroomAI` كـ build context. ضع `RECOGNITION_API_KEY` نفسه الموجود في Node. المنفذ الداخلي 8001؛ health path هو `/health`. لو استضافتك تفرض منفذًا آخر، شغّل `python -m uvicorn recognition_service.main:app --host 0.0.0.0 --port $PORT --workers 1 --limit-concurrency 8 --no-access-log`. الملف الافتراضي للحاوية يستخدم 8001.
- **Node:** من مجلد الباك إند نفّذ build command `npm ci` وstart command `npm start`، أو استخدم Dockerfile الموجود. عيّن `NODE_ENV=production` و`RECOGNITION_URL` لعنوان Python القابل للوصول من الخادم، بجانب قيم قاعدة البيانات والتخزين والأسرار. `/health` يختبر قاعدة البيانات. Node يقرأ `PORT` الذي توفره المنصة، وافتراضيه 4000.
- **Next.js:** من مجلد الفرونت نفّذ `npm ci && npm run build` ثم `npm start -- --hostname 0.0.0.0 --port $PORT` على منصة Linux. عيّن متغير الخادم `CLASSROOM_API_URL=https://YOUR_NODE_HOST/api/v1`، أو عنوانه الداخلي إن كانت الخدمات تشترك في شبكة خاصة. يجب أن يكون رابط الواجهة HTTPS حتى تعمل cookie الإنتاج والكاميرا. جميع طلبات المتصفح تمر عبر `/api/backend` على نفس نطاق الواجهة.

يفضل أن تكون Python وNode على شبكة خاصة. إذا كانت خطة التجربة تعرض Python على رابط عام، استخدم HTTPS ومفتاح التعرف السري؛ لا تضع ذلك المفتاح في الفرونت. لا تستخدم عنوان `127.0.0.1` بين خدمتين منشورتين على مضيفين منفصلين.

يمكن تشغيل الستاك محليًا عبر `docker compose up --build` من الباك إند بعد توفير `POSTGRES_PASSWORD` والأسرار في البيئة. هذا compose تجريبي: يضبط Node على development ويستخدم volumes محلية، ويعرض الواجهة على `localhost:3000` والباك إند على `127.0.0.1:4000`. لا تعتبره إعداد نشر HTTPS جاهزًا. Docker غير متاح في جهاز التحقق الحالي؛ لم يُختبر بناء الصور أو تشغيل compose هنا.

## 4. الحدود المجانية

Supabase Free يتضمن حاليًا **500 MB لقاعدة البيانات و1 GB للتخزين**، ويتوقف المشروع بعد أسبوع من عدم النشاط؛ النسخ الاحتياطية الآلية ليست ضمن الخطة المجانية. احسب الصور وحركة النقل وراقب لوحة الاستخدام. [حدود Supabase الرسمية](https://supabase.com/pricing).

Render يمكن استخدامه لتجربة web services، لكنه يمنح **750 ساعة تشغيل مجانية مشتركة لكل workspace شهريًا**، وليس لكل خدمة على حدة. تنام الخدمة بعد 15 دقيقة دون حركة واردة، والعودة قد تؤخر أول طلب. الملفات المحلية مؤقتة وتُفقد عند إعادة النشر أو التشغيل أو النوم، لذا لا تحفظ صور الطلاب عليها. تراجع أيضًا حدود الذاكرة والنقل والبناء في [وثائق Render Free](https://render.com/docs/free).

تشغيل Next وNode وPython معًا يستهلك الرصيد المشترك. لم يُقَس أداء dlib على معالج الخطة المجانية وذاكرتها؛ لا يوجد ضمان أنها تكفي للتعرف الحي. جرّب إنشاء الطالب وصورة واحدة، ثم قِس زمن معالجة الإطار والذاكرة وعدد أخطاء 429/502 قبل زيادة العدد. يمكن إبقاء تجربة التعرف محلية إلى حين اختيار استضافة مناسبة بدل الادعاء أن كامل الستاك سيعمل مجانًا دائمًا.

## 5. التحقق بعد النشر

تحقق من `/health` في Node وPython، ثم سجل دخولك من واجهة HTTPS. أنشئ مدرسة ومرحلة وفصلًا، واضبط المنطقة الزمنية وأوقات الحضور. أضف طالبًا بصورة وجه حقيقية مصرح باستخدامها، وتأكد أن الصورة لا تُفتح خارج جلسة الدخول. جرّب الحضور والتأخير والتصحيح اليدوي بثلاثة إطارات واضحة، وصورة لا تخص أي طالب للتأكد من عدم تسجيل تطابق غير مؤكد. لا تعتبر اختبار الإطار الفارغ قياسًا للدقة.

حساب واحد يدير جميع المدارس حاليًا؛ هذه نسخة تجربة وليست منصة متعددة الجهات بصلاحيات معزولة. الجداول تحفظ snapshots للجدول والمنطقة الزمنية، والتعديل يسري من اليوم التالي. الغياب يُستنتج عند قراءة/تحديث اليوم بعد مهلة الحضور، ولا توجد عملية خلفية ترسل تقارير في وقت محدد. لا توجد liveness أو حماية من تصوير صورة شخص؛ راجع سجل الحضور يدويًا عند الشك.

## 6. نسخة احتياطية قابلة للاستعادة

احتفظ بنسخة PostgreSQL **ونسخة ملفات الصور منفصلة**؛ `pg_dump` لا ينسخ محتوى Supabase Storage. خزّن النسخ في مكان خاص مع تاريخ النسخة، واحتفظ بمفاتيح `storage_key` وأسماء الصور كما هي. سجل نموذج التعرف `dlib-v1` مع النسخة، لأن embeddings محفوظة في قاعدة البيانات.

مثال PostgreSQL المحلي باستخدام ملف كلمات مرور PostgreSQL الخاص بك، دون وضع كلمة المرور في سطر الأوامر:

```powershell
$backupStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $env:LOCALAPPDATA 'ClassroomAI\backups'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' -h 127.0.0.1 -p 55432 -U classroom -d classroom_ai -Fc -f (Join-Path $backupDir "classroom-ai-$backupStamp.dump")
if ($LASTEXITCODE -ne 0) { throw 'Database backup failed' }
```

استخدم اسم مستخدم قاعدة البيانات الفعلي في `.env` إن اختلف عن `classroom`؛ سيطلب `pg_dump` كلمة المرور إن لم يكن ملف كلمات المرور مهيأ. لـ Supabase انسخ host/user/port الصحيحين من Connect واستخدم TLS؛ الاتصال المباشر هو المفضل للنسخ الاحتياطية وفق [دليل الاتصال](https://supabase.com/docs/guides/database/connecting-to-postgres).

في وضع `STORAGE_PROVIDER=local`، انسخ مجلد `UPLOAD_DIR` إلى مجلد نسخة جديد أثناء إيقاف عمليات إضافة/حذف الصور مؤقتًا. في وضع Supabase صدّر جميع objects من bucket الخاص إلى أرشيف خاص باستخدام أداة Storage/S3 مصرح لها، مع الحفاظ على المسارات؛ نسخة SQL وحدها لا تكفي. لا ترفع ملفات النسخ أو `.env` إلى Git.

لا تستعد فوق قاعدة حالية افتراضيًا. أنشئ قاعدة **جديدة فارغة** للتجربة، ثم استخدم `pg_restore --no-owner --no-privileges --dbname=NEW_EMPTY_DATABASE PATH_TO_DUMP` بالإعدادات الصحيحة. استعد الصور إلى مكان خاص منفصل، ثم شغّل نسخة اختبار من التطبيق عليها وتحقق من الطلاب والسجلات والصور قبل أي تحويل للإنتاج. لا تستخدم `--clean` أو drop لقاعدة التشغيل كجزء من روتين الاستعادة.
