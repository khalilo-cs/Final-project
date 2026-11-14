# AI Project Examiner — نظام فاحص المشاريع الذكي

نظام لمناقشة وتقييم مشاريع التخرج البرمجية بالذكاء الاصطناعي: تحليل الكود والأمان وقاعدة
البيانات والتقرير، مناقشة الطالب بأسئلة مولّدة من كوده، وكشف الغش.

مشروع تخرج — جامعة صنعاء، كلية الحاسوب وتكنولوجيا المعلومات.
الخطة الكاملة: [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).

## الحالة الحالية

المنجز حتى الآن: تجهيز البيئة (أسبوع 3)، محرك تحليل الكود (أسابيع 4، 6، 7) للغتي
Python و Java، محلل قاعدة البيانات (أسابيع 8، 9)، ومحلل التقارير (أسابيع 10، 11):

| الخدمة | المنفذ | الحالة |
|--------|--------|--------|
| `auth-service` | 8001 | تسجيل، دخول، JWT (access + refresh مع تدوير وإبطال)، ثلاثة أدوار، إدارة المستخدمين للـ admin |
| `project-service` | 8002 | المواد، تسجيل الطلاب فيها، رفع المشروع (ZIP + تقرير PDF/DOCX + ملف SQL)، تشغيل التحليلات تلقائياً وحفظ نتائجها، الدرجة المقترحة مع التبرير، أوزان التقييم لكل مادة، تنبيهات الدكتور، كشف الدرجات Excel |
| `code-analyzer` | 8003 | رفع ZIP ← بنية الكود (AST)، التعقيد (Cyclomatic + Cognitive)، Code Smells، فحص أمني، درجتا الجودة والأمان |
| `db-analyzer` | 8004 | ملف SQL (MySQL / PostgreSQL / SQLite) ← المفاتيح، التطبيع، أنواع البيانات، الاستعلامات، مخطط ER، درجة قاعدة البيانات |
| `report-analyzer` | 8005 | تقرير PDF/DOCX ← كشف الانتحال مقابل كل التقارير السابقة، التناقض بين التقرير والكود، جودة التوثيق، درجة التقرير |

ما يكشفه الفحص الأمني حالياً:

| | Python | Java |
|---|---|---|
| SQL Injection (concatenation، format، متغير بُني ديناميكياً) | ✅ | ✅ (JDBC، JPA، JdbcTemplate) |
| Command Injection | ✅ | ✅ (`Runtime.exec`، `ProcessBuilder` مع shell) |
| Insecure Deserialization | ✅ (pickle، yaml) | ✅ (`ObjectInputStream`، `XMLDecoder`) |
| XSS | — | ✅ (مدخلات الطلب تُكتب في الـ response) |
| Path Traversal | — | ✅ (`File`/`Paths.get` من مدخلات الطلب) |
| تشفير / hash ضعيف | ✅ | ✅ (MD5، SHA-1، DES، ECB) |
| `eval`، `debug=True`، `verify=False` | ✅ | — |
| Hardcoded Secrets | ✅ لكل اللغات وملفات الإعداد | |

### لم يُنفَّذ بعد

باقي الخدمات في الخطة (api-gateway،
viva-engine، fraud-detector، sandbox-runner، report-generator)، الواجهة (React)، محللات
JavaScript/C#/C++، Knowledge Graph، كشف التكرار والـ Dead Code، و Alembic migrations.

## التشغيل

```bash
cp .env.example .env      # ثم املأ JWT_SECRET وكلمات المرور
docker compose up --build
```

- توثيق الـ API التفاعلي: `/docs` على كل منفذ (8001 إلى 8005).
- أول حساب admin يُنشأ من `ADMIN_*` في `.env` عند أول تشغيل.

مثال كامل (دكتور ينشئ مادة ويسجّل طالباً، والطالب يرفع مشروعه):

```bash
login() { curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d "{\"username\":\"$1\",\"password\":\"$2\"}" | jq -r .access_token; }

FAC=$(login dr.ali '<password>')     # حساب faculty يُنشئه الـ admin عبر POST /api/v1/users
STU=$(login sara '<password>')       # حساب طالب عبر POST /api/v1/auth/register

CID=$(curl -s localhost:8002/api/v1/courses -H "Authorization: Bearer $FAC" \
  -H 'content-type: application/json' -d '{"name":"مشروع التخرج","code":"CS499"}' | jq -r .id)
curl -s localhost:8002/api/v1/courses/$CID/students -H "Authorization: Bearer $FAC" \
  -H 'content-type: application/json' -d '{"student_ids":["<student-uuid>"]}'

PID=$(curl -s localhost:8002/api/v1/projects -H "Authorization: Bearer $STU" \
  -F title="نظام مكتبة" -F course_id=$CID -F code=@code.zip -F report=@report.pdf \
  -F database=@schema.sql | jq -r .id)

curl -s localhost:8002/api/v1/projects/$PID/status -H "Authorization: Bearer $STU"
curl -s localhost:8002/api/v1/analysis/security/$PID/results -H "Authorization: Bearer $FAC"
curl -s localhost:8002/api/v1/analysis/database/$PID/results -H "Authorization: Bearer $FAC"
curl -s localhost:8002/api/v1/analysis/database/$PID/er-diagram -H "Authorization: Bearer $FAC"
curl -s localhost:8002/api/v1/analysis/report/$PID/results -H "Authorization: Bearer $FAC"
```

### الدرجات ولوحة الدكتور

- `GET /api/v1/grades/{project_id}`: الدرجة المقترحة بأوزان الخطة (الكود 20، الأمان 10،
  قاعدة البيانات 10، التقرير 15، المناقشة 25، الأصالة 10، الأداء 10)، مع سطر تبرير لكل
  معيار من نتائج التحليل، ونسبة **التغطية**: المعايير التي لم تُبنَ خدماتها بعد (المناقشة،
  الأصالة، الأداء) لا تُحسب صفراً، بل تُحسب الدرجة على المتوفر وتُعرض التغطية (حالياً 55%).
- `PUT /api/v1/grades/{project_id}`: الدكتور يعتمد الدرجة النهائية مع ملاحظة. كل اعتماد
  يُسجَّل في `learning_log` مع اقتراح النظام لحظتها، لتعلّم الأوزان لاحقاً (المرحلة 8).
- الطالب لا يرى الدرجة المقترحة؛ يرى الدرجة النهائية فقط بعد اعتمادها.
- `GET/PUT /api/v1/courses/{id}/criteria`: أوزان المادة (مجموعها 100).
- `GET /api/v1/grades/course/{id}` و `GET /api/v1/reports/course/{id}/excel`: كشف درجات
  المادة بأسماء الطلاب وأرقامهم الجامعية (من auth-service)، ملف Excel من اليمين لليسار،
  ومحمي من حقن الصيغ في النصوص التي يكتبها الطلاب.
- `GET /api/v1/dashboard/faculty/summary` و `/alerts`: ملخص مشاريع الدكتور وتنبيهات
  مرتبة حسب الخطورة: انتحال ≥ 30% (High) أو ≥ 15%، ثغرات حرجة، تناقض التقرير مع الكود،
  فشل التحليل، جداول بلا مفتاح أساسي.

### ما يكشفه محلل التقارير

- **الانتحال (عربي + إنجليزي):** بصمات Winnowing (نفس فكرة MOSS) على مقاطع من 5 كلمات،
  مقابل كل تقرير سُلِّم سابقاً في النظام (كل المواد والدفعات). أي مقطع منسوخ من 8 كلمات
  فأكثر يُكتشف مضموناً. النص العربي يُوحَّد قبل المقارنة (التشكيل، التطويل، أشكال الألف،
  ى/ي، ة/ه، الأرقام الهندية، وأشكال الحروف في ملفات PDF)، فتغيير التشكيل أو الهمزات لا
  يخفي النسخ. العبارات المشتركة بين 30% من التقارير فأكثر (ترويسة الجامعة، عناوين القالب)
  تُستبعد تلقائياً. النتيجة: النسبة، المشاريع المصدر، والمقاطع المنسوخة بنصها.
  الدكتور يرى المشروع المصدر وصاحبه؛ الطالب يرى النسبة والمقاطع فقط.
- **التناقض مع الكود:** محلل الكود يستخرج التقنيات المستخدمة فعلاً (من `package.json`،
  `requirements.txt`، `pom.xml`، `composer.json`، الـ imports، ونصوص الاتصال مثل
  `jdbc:mysql`) واللغات وبنية المجلدات. ثم يُقارَن بما يذكره التقرير: تقنية مذكورة غير
  موجودة (Medium إن تكررت 3 مرات فأكثر، Low لذكر عابر قد يكون في الدراسات السابقة)، تقنية
  مستخدمة لم تُوثَّق، ادعاء MVC بلا بنية MVC، وعدد جداول يخالف قاعدة البيانات المسلّمة.
- **جودة التوثيق:** وجود الفصول الأساسية (مقدمة، المشكلة، الأهداف، الدراسات السابقة،
  المتطلبات، التصميم، التنفيذ، الاختبار، الخاتمة، المراجع)، عدد المراجع، الأشكال والجداول،
  والطول.

حدود معروفة: لا مقارنة مع الإنترنت بعد (المقارنة داخل قاعدة النظام فقط)، والتقارير
الممسوحة ضوئياً (صور بلا نص) تُعطي تحذيراً بدل نتيجة لأن OCR غير مدعوم بعد.

### ما يكشفه محلل قاعدة البيانات

| الفئة | الفحوصات |
|---|---|
| المفاتيح | جدول بلا Primary Key، عمود `user_id` بلا Foreign Key (مع اقتراح الأمر المصحِّح)، مرجع لجدول/عمود غير موجود، مرجع لعمود ليس PK أو UNIQUE، اختلاف النوع بين FK والعمود المرجعي، FK بلا index (PostgreSQL/SQLite) |
| التطبيع (تقديري) | 1NF: أعمدة مكررة `phone1, phone2` وقوائم في حقل واحد. 2NF: عمود يعتمد على جزء من مفتاح مركّب. 3NF: نسخ عمود من الجدول المرجعي (`customer_name` مع `customer_id`) |
| أنواع البيانات | كلمة مرور بطول لا يكفي لـ hash، FLOAT للمبالغ المالية، تاريخ كنص، رقم هاتف كـ INT، علَم كنص |
| الاستعلامات | `UPDATE`/`DELETE` بلا `WHERE`، `SELECT *` |

يفهم ملفات `mysqldump` و phpMyAdmin كما هي (`DELIMITER`، تعليقات `/*!40101 */`،
`LOCK TABLES`، و `ALTER TABLE ... ADD PRIMARY KEY` بعد الإنشاء)، ويتجاهل بيانات
`INSERT` دون تحليلها. مخطط ER يُولَّد بصيغة Mermaid ويُعرض مباشرة في GitHub والواجهة.

## التطوير

```bash
make install   # بيئة افتراضية + الاعتماديات
make test      # اختبارات كل الخدمات
make lint      # ruff
```

يتطلب Python 3.12 أو أحدث. الـ CI (GitHub Actions) يشغّل الفحص والاختبارات عند كل push.

## الهيكل

```
services/
  auth-service/      FastAPI + SQLAlchemy (PostgreSQL)
  project-service/   FastAPI + SQLAlchemy — courses/ projects/ analysis results
  code-analyzer/     FastAPI — analyzers/ quality/ security/
  db-analyzer/       FastAPI — parsers/ (SQL splitter + schema) analyzers/
  report-analyzer/   FastAPI — parsers/ (PDF, DOCX) text/ (Arabic) analyzers/ (winnowing…)
docs/PROJECT_PLAN.md الخطة الكاملة للمشروع
docker-compose.yml   postgres + الخدمات (و redis/rabbitmq/minio عبر --profile infra)
```

## اختلافات مقصودة عن الخطة

- **PyJWT بدل python-jose** — مكتبة python-jose قليلة الصيانة.
- **محلل Python يستخدم مكتبة `ast` القياسية** بدل Tree-sitter؛ أدق لـ Python. محلل Java
  يستخدم Tree-sitter، وكلاهما خلف نفس الواجهة `BaseAnalyzer` وبنفس قواعد حساب التعقيد
  حتى تكون الدرجات قابلة للمقارنة بين اللغات.
- **التحليل يعمل كـ background task داخل project-service** ويستدعي code-analyzer عبر
  HTTP؛ سينتقل إلى RabbitMQ worker لاحقاً. الملفات تُحفظ على القرص (MinIO لاحقاً).
- **لا foreign key بين المشاريع وجدول المستخدمين** لأن كل خدمة لها قاعدة بياناتها؛
  هوية المستخدم ودوره تؤخذ من الـ JWT.
- **التطبيع مستنتج من أسماء الأعمدة والمفاتيح**: لا يمكن إثبات الاعتماديات الوظيفية من
  الـ Schema وحده، لذا كل ملاحظة تذكر سببها ليحكم عليها الدكتور. BCNF غير مُقدَّر.
- **مخطط قاعدة البيانات في الخطة يستخدم `ENUM(...)` بصيغة MySQL** وهي غير صالحة في
  PostgreSQL؛ الجداول تُعرَّف عبر نماذج SQLAlchemy في كل خدمة.
- **درجات الجودة والأمان حالياً معادلات بسيطة** (`code-analyzer/app/quality/score.py`)
  تحتاج معايرة على تقييمات حقيقية. درجة جودة الكود تقيس النظافة لا حجم العمل: مشروع صغير
  نظيف يأخذ درجة عالية، لذا يبقى قرار الدكتور هو الحاسم.
