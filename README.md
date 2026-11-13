# AI Project Examiner — نظام فاحص المشاريع الذكي

نظام لمناقشة وتقييم مشاريع التخرج البرمجية بالذكاء الاصطناعي: تحليل الكود والأمان وقاعدة
البيانات والتقرير، مناقشة الطالب بأسئلة مولّدة من كوده، وكشف الغش.

مشروع تخرج — جامعة صنعاء، كلية الحاسوب وتكنولوجيا المعلومات.
الخطة الكاملة: [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).

## الحالة الحالية

المشروع في بدايته. المنجز حتى الآن يغطي تجهيز البيئة (أسبوع 3) وأول شريحة عاملة من
محرك تحليل الكود (أسابيع 4، 6، 7) للغة Python:

| الخدمة | المنفذ | الحالة |
|--------|--------|--------|
| `auth-service` | 8001 | تسجيل، دخول، JWT (access + refresh مع تدوير وإبطال)، ثلاثة أدوار، إدارة المستخدمين للـ admin |
| `code-analyzer` | 8003 | رفع ZIP ← بنية الكود (AST)، التعقيد (Cyclomatic + Cognitive)، Code Smells، فحص أمني، درجتا الجودة والأمان |

ما يكشفه الفحص الأمني حالياً (Python): SQL Injection، Command/Code Injection،
Insecure Deserialization، تعطيل التحقق من TLS، `debug=True`، خوارزميات hash ضعيفة،
و Hardcoded Secrets (لأي لغة).

### لم يُنفَّذ بعد

باقي الخدمات في الخطة (project-service، api-gateway، db-analyzer، report-analyzer،
viva-engine، fraud-detector، sandbox-runner، report-generator)، الواجهة (React)، محلل Java
وباقي اللغات، Knowledge Graph، كشف التكرار والـ Dead Code، و Alembic migrations.

## التشغيل

```bash
cp .env.example .env      # ثم املأ JWT_SECRET وكلمات المرور
docker compose up --build
```

- توثيق الـ API التفاعلي: <http://localhost:8001/docs> و <http://localhost:8003/docs>
- أول حساب admin يُنشأ من `ADMIN_*` في `.env` عند أول تشغيل.

مثال كامل:

```bash
TOKEN=$(curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' | jq -r .access_token)

zip -r project.zip my-project/
curl -s -F file=@project.zip -H "Authorization: Bearer $TOKEN" \
  localhost:8003/api/v1/analysis/code | jq .security
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
  code-analyzer/     FastAPI — analyzers/ quality/ security/
docs/PROJECT_PLAN.md الخطة الكاملة للمشروع
docker-compose.yml   postgres + الخدمات (و redis/rabbitmq/minio عبر --profile infra)
```

## اختلافات مقصودة عن الخطة

- **PyJWT بدل python-jose** — مكتبة python-jose قليلة الصيانة.
- **محلل Python يستخدم مكتبة `ast` القياسية** بدل Tree-sitter؛ أدق لـ Python وبدون
  اعتماديات. Tree-sitter سيُستخدم لـ Java وباقي اللغات خلف نفس الواجهة `BaseAnalyzer`.
- **`POST /api/v1/analysis/code` يستقبل ZIP ويعيد النتيجة مباشرة**؛ سيتحول إلى
  `/analysis/code/{project_id}` غير المتزامن بعد بناء project-service وطابور الرسائل.
- **مخطط قاعدة البيانات في الخطة يستخدم `ENUM(...)` بصيغة MySQL** وهي غير صالحة في
  PostgreSQL؛ الجداول تُعرَّف عبر نماذج SQLAlchemy في كل خدمة.
- **درجات الجودة والأمان حالياً معادلات بسيطة** (`code-analyzer/app/quality/score.py`)
  تحتاج معايرة على تقييمات حقيقية.
