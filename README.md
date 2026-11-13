# AI Project Examiner — نظام فاحص المشاريع الذكي

نظام لمناقشة وتقييم مشاريع التخرج البرمجية بالذكاء الاصطناعي: تحليل الكود والأمان وقاعدة
البيانات والتقرير، مناقشة الطالب بأسئلة مولّدة من كوده، وكشف الغش.

مشروع تخرج — جامعة صنعاء، كلية الحاسوب وتكنولوجيا المعلومات.
الخطة الكاملة: [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).

## الحالة الحالية

المشروع في بدايته. المنجز حتى الآن يغطي تجهيز البيئة (أسبوع 3) وأول شريحة عاملة من
محرك تحليل الكود (أسابيع 4، 6، 7) للغتي Python و Java:

| الخدمة | المنفذ | الحالة |
|--------|--------|--------|
| `auth-service` | 8001 | تسجيل، دخول، JWT (access + refresh مع تدوير وإبطال)، ثلاثة أدوار، إدارة المستخدمين للـ admin |
| `project-service` | 8002 | المواد، تسجيل الطلاب فيها، رفع المشروع (ZIP + تقرير PDF/DOCX)، تشغيل التحليل تلقائياً وحفظ نتائجه |
| `code-analyzer` | 8003 | رفع ZIP ← بنية الكود (AST)، التعقيد (Cyclomatic + Cognitive)، Code Smells، فحص أمني، درجتا الجودة والأمان |

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

باقي الخدمات في الخطة (api-gateway، db-analyzer، report-analyzer،
viva-engine، fraud-detector، sandbox-runner، report-generator)، الواجهة (React)، محللات
JavaScript/C#/C++، Knowledge Graph، كشف التكرار والـ Dead Code، و Alembic migrations.

## التشغيل

```bash
cp .env.example .env      # ثم املأ JWT_SECRET وكلمات المرور
docker compose up --build
```

- توثيق الـ API التفاعلي: <http://localhost:8001/docs>، <http://localhost:8002/docs>،
  <http://localhost:8003/docs>
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
  -F title="نظام مكتبة" -F course_id=$CID -F code=@code.zip -F report=@report.pdf | jq -r .id)

curl -s localhost:8002/api/v1/projects/$PID/status -H "Authorization: Bearer $STU"
curl -s localhost:8002/api/v1/analysis/security/$PID/results -H "Authorization: Bearer $FAC"
```

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
- **مخطط قاعدة البيانات في الخطة يستخدم `ENUM(...)` بصيغة MySQL** وهي غير صالحة في
  PostgreSQL؛ الجداول تُعرَّف عبر نماذج SQLAlchemy في كل خدمة.
- **درجات الجودة والأمان حالياً معادلات بسيطة** (`code-analyzer/app/quality/score.py`)
  تحتاج معايرة على تقييمات حقيقية.
