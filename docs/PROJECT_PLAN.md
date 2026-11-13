# AI Project Examiner — نظام مناقشة المشاريع الجامعية بالذكاء الاصطناعي
# خطة المشروع الكاملة

---

## 📋 معلومات المشروع

| البند | التفاصيل |
|-------|----------|
| اسم المشروع | AI Project Examiner (نظام فاحص المشاريع الذكي) |
| النوع | مشروع تخرج — علوم حاسوب |
| الجامعة | جامعة صنعاء — كلية الحاسوب وتكنولوجيا المعلومات |
| المدة المتوقعة | 7-8 أشهر |
| حجم الفريق المثالي | 3-5 أشخاص |

---

## 1. وصف المشروع

### 1.1 المشكلة
- الدكتور الجامعي يناقش 30-50 مشروع تخرج في فترة قصيرة مما يؤدي لمناقشات سطحية
- بعض الطلاب يسلّمون مشاريع منسوخة من الإنترنت أو من طلاب آخرين دون اكتشاف ذلك
- لا يوجد معيار موحّد للتقييم — كل دكتور يقيّم بطريقته
- لا يتم فحص جودة الكود أو الأمان أو الأداء بشكل منهجي
- التقارير المكتوبة قد لا تعكس المشروع الفعلي (تناقضات بين التقرير والكود)

### 1.2 الحل المقترح
نظام ذكي متكامل يقوم بـ:
1. تحليل الكود المصدري تحليلاً عميقاً (بنية، جودة، أمان، أداء)
2. تحليل قاعدة البيانات (تطبيع، استعلامات، تصميم)
3. تحليل التقرير المكتوب (انتحال، تناقضات مع الكود)
4. مناقشة الطالب بأسئلة ذكية مولّدة من كوده الفعلي
5. كشف الغش بثلاث طبقات (كود، سلوك، مناقشة)
6. تشغيل المشروع في بيئة معزولة وقياس الأداء
7. توليد تقارير تقييم شاملة للدكتور
8. التعلم المستمر من ملاحظات الدكتور

### 1.3 الأهداف
- تقليل وقت تقييم المشروع الواحد بنسبة 60%
- رفع دقة كشف الغش إلى 90%+
- توفير تقييم موحّد ومعياري لكل المشاريع
- مساعدة الطالب في تحسين مشروعه قبل التسليم النهائي
- بناء قاعدة معرفة من المشاريع السابقة

---

## 2. المتطلبات الوظيفية (Functional Requirements)

### FR-01: إدارة المستخدمين
- FR-01.1: تسجيل دخول بثلاثة أدوار (Admin, Faculty, Student)
- FR-01.2: إدارة الصلاحيات لكل دور
- FR-01.3: ربط الطلاب بالمواد والدكاترة
- FR-01.4: تسجيل دخول بحساب الجامعة (LDAP/OAuth)

### FR-02: رفع المشاريع
- FR-02.1: رفع الكود المصدري (ZIP, Git repo URL)
- FR-02.2: رفع التقرير (PDF, DOCX)
- FR-02.3: رفع ملف قاعدة البيانات (SQL dump, Schema)
- FR-02.4: تحديد اللغة/اللغات البرمجية المستخدمة
- FR-02.5: تحديد التقنيات والأطر المستخدمة
- FR-02.6: رفع رابط Git repository (اختياري)

### FR-03: تحليل الكود
- FR-03.1: بناء AST لكل ملف مصدري
- FR-03.2: بناء Knowledge Graph للمشروع كامل
- FR-03.3: حساب Code Complexity (Cyclomatic + Cognitive)
- FR-03.4: كشف Code Smells (دوال طويلة، كود متكرر، God Classes)
- FR-03.5: كشف Design Patterns المستخدمة
- FR-03.6: فحص SOLID Principles
- FR-03.7: كشف Dead Code
- FR-03.8: تحليل التبعيات (Dependencies)
- FR-03.9: دعم اللغات: Python, Java, C++, C#, JavaScript/TypeScript

### FR-04: تحليل الأمان
- FR-04.1: كشف SQL Injection
- FR-04.2: كشف XSS (Cross-Site Scripting)
- FR-04.3: كشف CSRF
- FR-04.4: كشف Hardcoded Secrets (كلمات مرور، مفاتيح API)
- FR-04.5: كشف Insecure Deserialization
- FR-04.6: كشف Path Traversal
- FR-04.7: كشف Command Injection
- FR-04.8: كشف Missing Input Validation
- FR-04.9: تصنيف الثغرات حسب الخطورة (Critical, High, Medium, Low)

### FR-05: تحليل قاعدة البيانات
- FR-05.1: قراءة Schema من MySQL, PostgreSQL, SQLite, MongoDB
- FR-05.2: تحليل التطبيع (1NF → BCNF)
- FR-05.3: كشف مفاتيح مفقودة (PK, FK)
- FR-05.4: كشف علاقات خاطئة أو مفقودة
- FR-05.5: تحليل الاستعلامات (N+1, missing indexes, SELECT *)
- FR-05.6: توليد ER Diagram تلقائياً
- FR-05.7: مقارنة الـ Schema مع ما هو مذكور في التقرير

### FR-06: تحليل التقرير
- FR-06.1: استخراج النص من PDF/DOCX
- FR-06.2: كشف الانتحال (عربي + إنجليزي)
- FR-06.3: مقارنة محتوى التقرير مع الكود الفعلي
- FR-06.4: كشف التناقضات (التقرير يذكر شيء غير موجود في الكود)
- FR-06.5: التحقق من UML Diagrams
- FR-06.6: تقييم جودة التوثيق

### FR-07: المناقشة الذكية
- FR-07.1: توليد أسئلة من الكود الفعلي للطالب
- FR-07.2: أسئلة متدرجة المستوى (فهم عام → تقني → تحدي → كشف)
- FR-07.3: تكيّف مستوى الأسئلة حسب إجابات الطالب
- FR-07.4: تقييم الإجابات بـ Confidence Score
- FR-07.5: مناقشة نصية (Chat)
- FR-07.6: مناقشة صوتية (Speech-to-Text + Text-to-Speech)
- FR-07.7: دعم العربية والإنجليزية
- FR-07.8: تسجيل كامل جلسة المناقشة
- FR-07.9: عرض الكود أثناء المناقشة مع تحديد الأسطر

### FR-08: كشف الغش
- FR-08.1: مقارنة Token-based بين المشاريع
- FR-08.2: مقارنة AST-based (حتى لو غيّر الأسماء)
- FR-08.3: مقارنة Semantic-based (فهم المنطق)
- FR-08.4: مقارنة مع قاعدة مشاريع سابقة
- FR-08.5: تحليل Git History (توزيع commits، أوقات، أنماط)
- FR-08.6: تحليل Coding Style Consistency
- FR-08.7: مقارنة أداء المناقشة مع جودة الكود
- FR-08.8: حساب Authenticity Score (0-100)

### FR-09: Sandbox وتحليل الأداء
- FR-09.1: تشغيل المشروع في Docker container معزول
- FR-09.2: قياس Response Time
- FR-09.3: قياس Memory Usage
- FR-09.4: قياس CPU Usage
- FR-09.5: Load Testing (محاكاة عدة مستخدمين)
- FR-09.6: كشف Memory Leaks
- FR-09.7: كشف Deadlocks
- FR-09.8: التقاط Screenshots للواجهة

### FR-10: لوحة تحكم الدكتور
- FR-10.1: عرض كل المشاريع المسلّمة
- FR-10.2: فلترة حسب المادة، الدفعة، نوع المشروع
- FR-10.3: مقارنة بين الطلاب بيانياً
- FR-10.4: تقرير PDF تلقائي لكل طالب
- FR-10.5: تصدير Excel للدرجات
- FR-10.6: تنبيهات (غش، مشاريع لا تعمل)
- FR-10.7: تعديل أوزان معايير التقييم
- FR-10.8: اقتراح الدرجة النهائية مع التبرير

### FR-11: التقارير والإحصائيات
- FR-11.1: تقرير تقييم شامل لكل طالب
- FR-11.2: إحصائيات على مستوى القسم
- FR-11.3: أكثر الأخطاء شيوعاً
- FR-11.4: توزيع الدرجات
- FR-11.5: مقارنة بين الفصول الدراسية
- FR-11.6: Trends (تحسّن المستوى مع الوقت)

### FR-12: التعلم المستمر
- FR-12.1: تعلّم من تعديلات الدكتور على الدرجات
- FR-12.2: تحسين أوزان التقييم تلقائياً
- FR-12.3: تحسين توليد الأسئلة
- FR-12.4: كشف أنماط غش جديدة
- FR-12.5: بناء Knowledge Base من المشاريع السابقة

---

## 3. المتطلبات غير الوظيفية (Non-Functional Requirements)

### NFR-01: الأداء
- تحليل مشروع متوسط (10,000 سطر) في أقل من 5 دقائق
- استجابة المناقشة في أقل من 3 ثوانٍ
- دعم 50 مشروع متزامن للتحليل
- دعم 20 جلسة مناقشة متزامنة

### NFR-02: الأمان
- تشفير البيانات في النقل (HTTPS/TLS)
- تشفير البيانات المخزنة (AES-256)
- Sandbox معزول تماماً (لا وصول للشبكة)
- Rate Limiting على الـ APIs
- RBAC (Role-Based Access Control)
- تسجيل كل العمليات (Audit Log)

### NFR-03: قابلية التوسع
- معمارية Microservices
- كل خدمة قابلة للتوسع أفقياً
- Message Queue للعمليات الثقيلة
- Caching للنتائج المتكررة

### NFR-04: سهولة الاستخدام
- واجهة عربية بالكامل مع دعم الإنجليزية
- واجهة متجاوبة (Desktop + Tablet)
- لا يتطلب تدريب مسبق للاستخدام
- توثيق شامل ودليل مستخدم

### NFR-05: الموثوقية
- Uptime 99%
- نسخ احتياطي يومي تلقائي
- استرجاع البيانات في أقل من ساعة
- معالجة الأخطاء بشكل graceful

---

## 4. المعمارية التقنية (System Architecture)

### 4.1 المعمارية العامة

```
                        ┌─────────────────────────┐
                        │      Load Balancer       │
                        │        (Nginx)           │
                        └───────────┬─────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            ┌───────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
            │   Frontend   │ │  WebSocket │ │   Static    │
            │   (React)    │ │  Server    │ │   Assets    │
            └───────┬──────┘ └─────┬──────┘ └─────────────┘
                    │              │
                    └──────┬───────┘
                           │
                    ┌──────▼──────┐
                    │  API Gateway │
                    │  (FastAPI)   │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────────┐
            │              │                  │
    ┌───────▼──────┐ ┌────▼─────┐  ┌─────────▼─────────┐
    │   Auth       │ │  Project │  │   Analysis        │
    │   Service    │ │  Service │  │   Orchestrator    │
    └──────────────┘ └──────────┘  └─────────┬─────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  Message Queue  │
                                    │  (RabbitMQ)     │
                                    └────────┬────────┘
                                             │
         ┌──────────┬──────────┬─────────┬───┴────┬──────────┐
         │          │          │         │        │          │
    ┌────▼───┐ ┌───▼────┐ ┌──▼───┐ ┌───▼──┐ ┌──▼───┐ ┌───▼────┐
    │ Code   │ │  DB    │ │Report│ │ Viva │ │Fraud │ │Sandbox │
    │Analyzer│ │Analyzer│ │Parser│ │Engine│ │Detect│ │Runner  │
    └────┬───┘ └───┬────┘ └──┬───┘ └───┬──┘ └──┬───┘ └───┬────┘
         │         │         │        │       │         │
         └─────────┴─────────┴────┬───┴───────┴─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
             ┌──────▼──────┐ ┌───▼───┐ ┌──────▼──────┐
             │ PostgreSQL  │ │MongoDB│ │   Neo4j     │
             │ (Users,     │ │(Logs, │ │ (Knowledge  │
             │  Grades,    │ │ Docs) │ │  Graph)     │
             │  Projects)  │ └───────┘ └─────────────┘
             └─────────────┘
                    │
             ┌──────▼──────┐ ┌─────────────┐
             │   Redis     │ │  ChromaDB   │
             │  (Cache,    │ │ (Vector DB  │
             │   Sessions) │ │  for RAG)   │
             └─────────────┘ └─────────────┘
```

### 4.2 الخدمات المصغرة (Microservices)

| الخدمة | المسؤولية | التقنية | المنفذ |
|--------|-----------|---------|--------|
| api-gateway | توجيه الطلبات، المصادقة | FastAPI | 8000 |
| auth-service | تسجيل دخول، صلاحيات، JWT | FastAPI | 8001 |
| project-service | إدارة المشاريع، الرفع | FastAPI | 8002 |
| code-analyzer | تحليل الكود، AST، Security | FastAPI | 8003 |
| db-analyzer | تحليل قواعد البيانات | FastAPI | 8004 |
| report-analyzer | تحليل التقارير، الانتحال | FastAPI | 8005 |
| viva-engine | المناقشة الذكية، توليد الأسئلة | FastAPI | 8006 |
| fraud-detector | كشف الغش، المقارنة | FastAPI | 8007 |
| sandbox-runner | تشغيل المشاريع المعزول | FastAPI | 8008 |
| report-generator | توليد التقارير PDF/Excel | FastAPI | 8009 |
| notification-service | التنبيهات والإشعارات | FastAPI | 8010 |

### 4.3 قاعدة البيانات (Database Schema)

```sql
-- المستخدمون
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role ENUM('admin', 'faculty', 'student') NOT NULL,
    department VARCHAR(100),
    student_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- المواد الدراسية
CREATE TABLE courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    faculty_id UUID REFERENCES users(id),
    semester VARCHAR(50),
    year INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- تسجيل الطلاب في المواد
CREATE TABLE enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID REFERENCES users(id),
    course_id UUID REFERENCES courses(id),
    UNIQUE(student_id, course_id)
);

-- المشاريع
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    student_id UUID REFERENCES users(id),
    course_id UUID REFERENCES courses(id),
    programming_languages TEXT[], -- ['Python', 'JavaScript']
    frameworks TEXT[], -- ['FastAPI', 'React']
    git_url VARCHAR(500),
    code_path VARCHAR(500),
    report_path VARCHAR(500),
    db_schema_path VARCHAR(500),
    status ENUM('submitted', 'analyzing', 'analyzed', 'viva_scheduled',
                'viva_completed', 'graded') DEFAULT 'submitted',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- نتائج تحليل الكود
CREATE TABLE code_analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    total_files INT,
    total_lines INT,
    total_classes INT,
    total_functions INT,
    cyclomatic_complexity_avg FLOAT,
    cognitive_complexity_avg FLOAT,
    code_duplication_percentage FLOAT,
    dead_code_lines INT,
    design_patterns_detected JSONB, -- [{"pattern": "Singleton", "file": "...", "line": 42}]
    solid_violations JSONB,
    code_smells JSONB,
    overall_quality_score FLOAT, -- 0-100
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- نتائج تحليل الأمان
CREATE TABLE security_analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    vulnerabilities JSONB, -- [{"type": "SQL Injection", "severity": "Critical", "file": "...", "line": 15, "description": "..."}]
    critical_count INT DEFAULT 0,
    high_count INT DEFAULT 0,
    medium_count INT DEFAULT 0,
    low_count INT DEFAULT 0,
    overall_security_score FLOAT, -- 0-100
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- نتائج تحليل قاعدة البيانات
CREATE TABLE db_analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    total_tables INT,
    normalization_level VARCHAR(10), -- '1NF', '2NF', '3NF', 'BCNF'
    missing_primary_keys TEXT[],
    missing_foreign_keys JSONB,
    missing_indexes JSONB,
    query_issues JSONB, -- [{"type": "N+1", "file": "...", "line": 23}]
    er_diagram_svg TEXT,
    overall_db_score FLOAT, -- 0-100
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- نتائج تحليل التقرير
CREATE TABLE report_analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    plagiarism_percentage FLOAT,
    plagiarism_sources JSONB, -- [{"text": "...", "source": "...", "similarity": 0.95}]
    inconsistencies JSONB, -- [{"report_claim": "Uses MVC", "code_reality": "No MVC pattern found"}]
    documentation_quality_score FLOAT,
    overall_report_score FLOAT, -- 0-100
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- جلسات المناقشة
CREATE TABLE viva_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    student_id UUID REFERENCES users(id),
    mode ENUM('text', 'voice') DEFAULT 'text',
    language ENUM('ar', 'en') DEFAULT 'ar',
    status ENUM('in_progress', 'completed', 'abandoned') DEFAULT 'in_progress',
    total_questions INT DEFAULT 0,
    correct_answers INT DEFAULT 0,
    partial_answers INT DEFAULT 0,
    wrong_answers INT DEFAULT 0,
    avg_confidence_score FLOAT,
    avg_response_time_seconds FLOAT,
    overall_viva_score FLOAT, -- 0-100
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    recording_path VARCHAR(500)
);

-- أسئلة وإجابات المناقشة
CREATE TABLE viva_qa (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES viva_sessions(id),
    question_number INT,
    difficulty_level INT, -- 1-4
    question_type ENUM('understanding', 'technical', 'challenge', 'verification'),
    question_text TEXT NOT NULL,
    related_code_file VARCHAR(500),
    related_code_lines VARCHAR(50), -- '47-55'
    student_answer TEXT,
    expected_answer_summary TEXT,
    confidence_score FLOAT, -- 0-100
    evaluation ENUM('correct', 'partial', 'wrong', 'evasive'),
    evaluation_notes TEXT,
    response_time_seconds FLOAT,
    asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- نتائج كشف الغش
CREATE TABLE fraud_detection_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    code_similarity_max FLOAT, -- أعلى تشابه مع مشروع آخر
    similar_projects JSONB, -- [{"project_id": "...", "similarity": 0.85, "method": "AST"}]
    git_analysis JSONB, -- {"total_commits": 3, "suspicious": true, "reasons": ["single commit"]}
    style_consistency_score FLOAT,
    viva_vs_code_gap FLOAT, -- الفرق بين أداء المناقشة وجودة الكود
    authenticity_score FLOAT, -- 0-100
    flags JSONB, -- [{"type": "single_commit", "severity": "high", "evidence": "..."}]
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- نتائج تحليل الأداء
CREATE TABLE performance_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    runs_successfully BOOLEAN,
    startup_time_ms INT,
    avg_response_time_ms INT,
    max_response_time_ms INT,
    memory_usage_mb FLOAT,
    cpu_usage_percent FLOAT,
    memory_leak_detected BOOLEAN DEFAULT FALSE,
    deadlock_detected BOOLEAN DEFAULT FALSE,
    load_test_results JSONB, -- {"concurrent_users": 100, "avg_response": 250, "errors": 2}
    screenshots JSONB, -- ["path1.png", "path2.png"]
    overall_performance_score FLOAT, -- 0-100
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- الدرجات النهائية
CREATE TABLE final_grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    code_quality_score FLOAT, -- الوزن: 20%
    security_score FLOAT, -- الوزن: 10%
    db_score FLOAT, -- الوزن: 10%
    report_score FLOAT, -- الوزن: 15%
    viva_score FLOAT, -- الوزن: 25%
    authenticity_score FLOAT, -- الوزن: 10%
    performance_score FLOAT, -- الوزن: 10%
    suggested_total FLOAT, -- المجموع المقترح من النظام
    faculty_adjusted_total FLOAT, -- المجموع بعد تعديل الدكتور
    faculty_notes TEXT,
    graded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- معايير التقييم القابلة للتعديل
CREATE TABLE grading_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID REFERENCES courses(id),
    criterion_name VARCHAR(100),
    weight FLOAT, -- النسبة من الدرجة الكلية
    description TEXT,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- سجل تعلّم النظام
CREATE TABLE learning_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type ENUM('grade_adjustment', 'question_feedback', 'fraud_override'),
    project_id UUID REFERENCES projects(id),
    original_value JSONB,
    adjusted_value JSONB,
    faculty_id UUID REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.4 الـ APIs الرئيسية

```
# المصادقة
POST   /api/v1/auth/login
POST   /api/v1/auth/register
POST   /api/v1/auth/refresh-token
POST   /api/v1/auth/logout

# المستخدمون
GET    /api/v1/users
GET    /api/v1/users/{id}
PUT    /api/v1/users/{id}
DELETE /api/v1/users/{id}

# المواد
GET    /api/v1/courses
POST   /api/v1/courses
GET    /api/v1/courses/{id}
GET    /api/v1/courses/{id}/students
GET    /api/v1/courses/{id}/projects

# المشاريع
POST   /api/v1/projects                    # رفع مشروع جديد
GET    /api/v1/projects/{id}               # تفاصيل المشروع
GET    /api/v1/projects/{id}/status         # حالة التحليل
DELETE /api/v1/projects/{id}

# تحليل الكود
POST   /api/v1/analysis/code/{project_id}          # بدء التحليل
GET    /api/v1/analysis/code/{project_id}/results   # النتائج
GET    /api/v1/analysis/code/{project_id}/graph      # Knowledge Graph

# تحليل الأمان
POST   /api/v1/analysis/security/{project_id}
GET    /api/v1/analysis/security/{project_id}/results

# تحليل قاعدة البيانات
POST   /api/v1/analysis/database/{project_id}
GET    /api/v1/analysis/database/{project_id}/results
GET    /api/v1/analysis/database/{project_id}/er-diagram

# تحليل التقرير
POST   /api/v1/analysis/report/{project_id}
GET    /api/v1/analysis/report/{project_id}/results
GET    /api/v1/analysis/report/{project_id}/plagiarism

# المناقشة
POST   /api/v1/viva/start/{project_id}              # بدء جلسة مناقشة
POST   /api/v1/viva/{session_id}/answer              # إرسال إجابة
GET    /api/v1/viva/{session_id}/next-question        # السؤال التالي
POST   /api/v1/viva/{session_id}/end                 # إنهاء المناقشة
GET    /api/v1/viva/{session_id}/transcript           # نص المناقشة
GET    /api/v1/viva/{session_id}/results              # نتائج المناقشة
WS     /ws/viva/{session_id}                          # WebSocket للمناقشة الحية

# كشف الغش
POST   /api/v1/fraud/analyze/{project_id}
GET    /api/v1/fraud/{project_id}/results
GET    /api/v1/fraud/{project_id}/similar-projects

# Sandbox والأداء
POST   /api/v1/sandbox/run/{project_id}
GET    /api/v1/sandbox/{project_id}/status
GET    /api/v1/sandbox/{project_id}/results
GET    /api/v1/sandbox/{project_id}/screenshots

# التقارير
GET    /api/v1/reports/student/{project_id}           # تقرير طالب
GET    /api/v1/reports/student/{project_id}/pdf        # تصدير PDF
GET    /api/v1/reports/course/{course_id}              # تقرير مادة
GET    /api/v1/reports/course/{course_id}/excel         # تصدير Excel
GET    /api/v1/reports/analytics/department             # إحصائيات القسم

# الدرجات
GET    /api/v1/grades/{project_id}
PUT    /api/v1/grades/{project_id}                     # تعديل الدكتور
GET    /api/v1/grades/course/{course_id}               # درجات المادة

# لوحة التحكم
GET    /api/v1/dashboard/faculty/summary
GET    /api/v1/dashboard/faculty/alerts
GET    /api/v1/dashboard/admin/stats
```

---

## 5. التقنيات المستخدمة (Technology Stack)

### 5.1 Frontend
| التقنية | الاستخدام |
|---------|-----------|
| React 18+ | واجهة المستخدم |
| TypeScript | لغة البرمجة |
| TailwindCSS | التصميم |
| Shadcn/UI | مكونات الواجهة |
| D3.js | الرسوم البيانية والـ Knowledge Graph |
| Monaco Editor | عرض الكود أثناء المناقشة |
| Socket.io Client | المناقشة الحية |
| React Query | إدارة الـ API calls |
| Zustand | إدارة الحالة |
| React Router v6 | التوجيه |
| i18next | دعم العربية والإنجليزية |
| Mermaid.js | عرض ER Diagrams و UML |

### 5.2 Backend
| التقنية | الاستخدام |
|---------|-----------|
| Python 3.11+ | اللغة الرئيسية |
| FastAPI | الـ API Framework |
| SQLAlchemy | ORM لقواعد البيانات |
| Alembic | Database Migrations |
| Celery | المهام الخلفية (Background Tasks) |
| Pydantic v2 | Data Validation |
| python-jose | JWT Authentication |
| WebSocket (FastAPI) | المناقشة الحية |

### 5.3 AI و ML
| التقنية | الاستخدام |
|---------|-----------|
| LLM (Llama 3 / Mistral) | توليد الأسئلة وفهم الإجابات |
| LangChain | إدارة الـ LLM Pipeline |
| ChromaDB | Vector Database للـ RAG |
| Sentence-BERT | مقارنة النصوص الدلالية |
| OpenAI Whisper | Speech-to-Text |
| gTTS / Coqui TTS | Text-to-Speech عربي |
| scikit-learn | تصنيف، تجميع، تقييم |
| Hugging Face Transformers | نماذج NLP عربية |

### 5.4 تحليل الكود
| التقنية | الاستخدام |
|---------|-----------|
| Tree-sitter | AST Parsing (متعدد اللغات) |
| Semgrep | Security Analysis |
| Radon (Python) | Complexity Analysis |
| PMD (Java) | Code Quality |
| ESLint (JS/TS) | Code Quality |
| NetworkX | بناء Code Dependency Graph |

### 5.5 قواعد البيانات
| التقنية | الاستخدام |
|---------|-----------|
| PostgreSQL 15+ | البيانات العلائقية الرئيسية |
| MongoDB | المستندات، التحليلات، السجلات |
| Neo4j | Knowledge Graph للكود |
| Redis | Caching + Sessions + Queue |
| ChromaDB | Vector embeddings للـ RAG |

### 5.6 DevOps والبنية التحتية
| التقنية | الاستخدام |
|---------|-----------|
| Docker | حاويات لكل خدمة |
| Docker Compose | تطوير محلي |
| Kubernetes (K8s) | نشر الإنتاج |
| GitHub Actions | CI/CD Pipeline |
| Nginx | Reverse Proxy + Load Balancer |
| RabbitMQ | Message Queue |
| Prometheus | مراقبة الأداء |
| Grafana | لوحة مراقبة |
| ELK Stack | تجميع وتحليل السجلات |
| MinIO | تخزين الملفات (S3-compatible) |

---

## 6. خطة التنفيذ التفصيلية (Week by Week)

### المرحلة 0: التأسيس (أسبوع 1-3)

#### أسبوع 1: البحث والدراسة
- [ ] دراسة الأنظمة المشابهة (CodeGrader, Codio, MOSS, Turnitin)
- [ ] قراءة 10-15 ورقة بحثية عن:
  - Automated Code Assessment
  - AI-based Question Generation
  - Code Plagiarism Detection
  - Adaptive Testing Systems
- [ ] تحليل نقاط القوة والضعف في الأنظمة الموجودة
- [ ] كتابة Literature Review (5-8 صفحات)
- [ ] تحديد الفجوة البحثية (Research Gap)

#### أسبوع 2: التصميم
- [ ] رسم System Architecture Diagram
- [ ] تصميم ERD كامل
- [ ] كتابة API Specification (OpenAPI/Swagger)
- [ ] تصميم الـ Wireframes للواجهة (Figma)
- [ ] كتابة SRS Document
- [ ] تصميم Use Case Diagrams
- [ ] تصميم Sequence Diagrams للعمليات الرئيسية
- [ ] تصميم Class Diagrams

#### أسبوع 3: تجهيز البيئة
- [ ] إنشاء GitHub Organization + Repositories
- [ ] إعداد Monorepo أو Multi-repo structure
- [ ] إعداد Docker Compose لكل الخدمات
- [ ] إعداد CI/CD Pipeline (GitHub Actions)
- [ ] إعداد قواعد البيانات (PostgreSQL, MongoDB, Neo4j, Redis, ChromaDB)
- [ ] إعداد RabbitMQ
- [ ] إعداد MinIO للملفات
- [ ] كتابة README وتوثيق بيئة التطوير
- [ ] إعداد Linting + Formatting (Black, ESLint, Prettier)
- [ ] إعداد Pre-commit hooks

---

### المرحلة 1: محرك تحليل الكود (أسبوع 4-7)

#### أسبوع 4: AST Parser Engine
- [ ] إعداد Tree-sitter مع grammars لكل لغة مدعومة
- [ ] بناء Python Analyzer:
  - استخراج classes, functions, imports, variables
  - كشف decorators, generators, context managers
- [ ] بناء Java Analyzer:
  - استخراج classes, interfaces, methods, fields
  - كشف annotations, generics, inheritance
- [ ] بناء JavaScript/TypeScript Analyzer:
  - استخراج classes, functions, arrow functions, modules
  - كشف async/await, promises, callbacks
- [ ] بناء C# Analyzer:
  - استخراج classes, interfaces, properties, methods
  - كشف LINQ, async/await, attributes
- [ ] بناء C++ Analyzer:
  - استخراج classes, templates, namespaces, functions
- [ ] واجهة موحّدة UnifiedAnalyzer تجمع كل اللغات
- [ ] كتابة Unit Tests لكل Analyzer

#### أسبوع 5: Knowledge Graph Builder
- [ ] تصميم Graph Schema في Neo4j
  - Nodes: File, Class, Function, Variable, Module
  - Edges: CALLS, INHERITS, IMPORTS, DEPENDS_ON, CONTAINS
- [ ] بناء GraphBuilder يحوّل AST → Neo4j Graph
- [ ] كتابة Cypher queries للاستعلام:
  - "ما الدوال التي تستدعي هذه الدالة؟"
  - "ما الكلاسات التي ترث من هذا الكلاس؟"
  - "ما التبعيات الدائرية؟"
- [ ] بناء REST API لاستعلام الـ Graph
- [ ] بناء Visualization بـ D3.js (Force-directed graph)
- [ ] كتابة Tests

#### أسبوع 6: Code Quality Analyzer
- [ ] Cyclomatic Complexity Calculator
- [ ] Cognitive Complexity Calculator
- [ ] Code Duplication Detector:
  - Token-based detection
  - AST-based detection (يكشف حتى لو غيّر الأسماء)
- [ ] Dead Code Detector
- [ ] Long Method Detector (threshold: 50 lines)
- [ ] God Class Detector (threshold: 500 lines, 20 methods)
- [ ] Circular Dependency Detector
- [ ] Design Pattern Detector:
  - Singleton, Factory, Observer, Strategy, MVC, Repository
- [ ] SOLID Principles Checker
- [ ] Overall Quality Score Calculator
- [ ] كتابة Tests

#### أسبوع 7: Security Scanner
- [ ] إعداد Semgrep مع custom rules
- [ ] SQL Injection Detector (pattern matching + taint analysis)
- [ ] XSS Detector
- [ ] CSRF Detector
- [ ] Hardcoded Secrets Scanner (regex + entropy-based)
- [ ] Path Traversal Detector
- [ ] Command Injection Detector
- [ ] Input Validation Checker
- [ ] Insecure Deserialization Detector
- [ ] Vulnerability Severity Classifier (Critical/High/Medium/Low)
- [ ] Security Report Generator
- [ ] كتابة Tests

---

### المرحلة 2: محلل قاعدة البيانات (أسبوع 8-9)

#### أسبوع 8: Schema Analyzer
- [ ] MySQL Schema Parser (من SQL dump)
- [ ] PostgreSQL Schema Parser
- [ ] SQLite Schema Parser
- [ ] MongoDB Schema Analyzer (من collection samples)
- [ ] Normalization Analyzer (1NF → BCNF)
- [ ] Missing Primary Key Detector
- [ ] Missing Foreign Key Detector
- [ ] Data Type Appropriateness Checker
- [ ] Index Recommendation Engine
- [ ] ER Diagram Generator (Mermaid.js syntax)
- [ ] كتابة Tests

#### أسبوع 9: Query Analyzer
- [ ] SQL Query Parser (sqlparse)
- [ ] N+1 Query Detector (يحلل الكود + الاستعلامات)
- [ ] SELECT * Detector
- [ ] Missing WHERE Clause Detector
- [ ] Unbounded Query Detector (no LIMIT)
- [ ] Suboptimal JOIN Detector
- [ ] Missing Transaction Detector
- [ ] SQL Injection in Queries Detector
- [ ] Query Performance Estimator
- [ ] Overall DB Score Calculator
- [ ] كتابة Tests

---

### المرحلة 3: محلل التقارير (أسبوع 10-11)

#### أسبوع 10: Document Parser + Plagiarism
- [ ] PDF Text Extractor (PyPDF2 + pdfplumber)
- [ ] DOCX Text Extractor (python-docx)
- [ ] Image/Diagram Extractor من المستندات
- [ ] Arabic Plagiarism Detector:
  - TF-IDF + Cosine Similarity
  - Sentence-BERT (Arabic model) للمقارنة الدلالية
  - Fingerprinting (Winnowing algorithm)
- [ ] English Plagiarism Detector
- [ ] مقارنة مع قاعدة المشاريع السابقة
- [ ] Plagiarism Report Generator
- [ ] كتابة Tests

#### أسبوع 11: Report vs Code Consistency
- [ ] Technology Claim Verifier:
  - التقرير يذكر "React" → هل package.json يحتوي react؟
  - التقرير يذكر "MySQL" → هل فيه MySQL connection؟
- [ ] Architecture Claim Verifier:
  - يذكر "MVC" → هل بنية المجلدات تعكس MVC؟
- [ ] Feature Claim Verifier:
  - يذكر "تسجيل دخول" → هل فيه login endpoint؟
- [ ] Table Count Verifier:
  - يذكر "10 جداول" → هل الـ Schema فيه 10؟
- [ ] UML Diagram Verifier (مقارنة مع الكود)
- [ ] Inconsistency Report Generator
- [ ] كتابة Tests

---

### المرحلة 4: نظام المناقشة الذكي (أسبوع 12-16)

#### أسبوع 12: Question Generation Engine
- [ ] إعداد RAG Pipeline:
  - Code Chunker (يقسّم الكود لأجزاء ذكية)
  - Embedding Generator (code → vectors)
  - ChromaDB Storage
- [ ] إعداد LLM (Llama 3 أو Mistral عبر Ollama)
- [ ] Question Templates لكل نوع:
  - understanding_templates.json
  - technical_templates.json
  - challenge_templates.json
  - verification_templates.json
- [ ] Context Builder: يجمع كل معلومات المشروع للـ LLM
- [ ] Question Generator: يولّد أسئلة محددة من الكود
- [ ] Question Ranker: يرتّب الأسئلة حسب الأهمية
- [ ] كتابة Tests + تقييم جودة الأسئلة

#### أسبوع 13: Adaptive Dialogue Manager
- [ ] Difficulty Level Controller (1-4)
- [ ] Answer Quality Estimator
- [ ] Dialogue State Tracker
- [ ] Topic Tracker (ما الموضوع الحالي في المناقشة)
- [ ] Evasion Detector (هل الطالب يتهرب؟)
- [ ] Follow-up Question Generator
- [ ] Conversation Flow Manager:
  - Opening → General → Technical → Deep → Closing
- [ ] Session Timer (حد أقصى 30 دقيقة)
- [ ] كتابة Tests

#### أسبوع 14: Answer Evaluation Engine
- [ ] Semantic Similarity Scorer:
  - مقارنة الإجابة مع الإجابة المتوقعة
  - استخدام Sentence-BERT
- [ ] Technical Accuracy Checker:
  - هل المصطلحات التقنية مستخدمة صحيحاً؟
- [ ] Vagueness Detector:
  - هل الإجابة عامة جداً بدون تفاصيل؟
- [ ] Contradiction Detector:
  - هل الطالب ناقض نفسه؟
- [ ] Confidence Score Calculator (0-100)
- [ ] Answer Classification (correct/partial/wrong/evasive)
- [ ] كتابة Tests

#### أسبوع 15: Voice + Chat Interface
- [ ] Chat Interface:
  - WebSocket server للمناقشة الحية
  - Real-time typing indicator
  - Code snippet display أثناء المناقشة
  - Line highlighting في الكود
- [ ] Voice Interface:
  - Whisper integration (Speech-to-Text)
  - Arabic TTS (Coqui TTS أو gTTS)
  - Audio streaming عبر WebSocket
  - Voice Activity Detection
- [ ] Session Recording:
  - تسجيل النص الكامل
  - تسجيل الصوت (إذا voice mode)
  - Timestamps لكل سؤال وإجابة
- [ ] كتابة Tests

#### أسبوع 16: Multi-language + UI Integration
- [ ] Arabic Question Templates
- [ ] English Question Templates
- [ ] Code-switching Handler (خلط عربي/إنجليزي)
- [ ] Technical Term Translator (عربي ↔ إنجليزي)
- [ ] Viva UI Component:
  - Split view: Chat + Code Editor
  - Question display
  - Timer
  - Progress indicator
  - الأسئلة المتبقية
- [ ] Integration Testing مع كل الموديولات
- [ ] كتابة Tests

---

### المرحلة 5: نظام كشف الغش (أسبوع 17-19)

#### أسبوع 17: Code Plagiarism Engine
- [ ] Token-based Comparator:
  - Tokenize الكود وتطبيع الأسماء
  - Running Karp-Rabin Greedy String Tiling
  - نسبة التشابه لكل زوج
- [ ] AST-based Comparator:
  - مقارنة بنية AST بدون أسماء
  - Tree Edit Distance
- [ ] Semantic Comparator:
  - Code2Vec أو CodeBERT embeddings
  - Cosine similarity على المستوى الدلالي
- [ ] قاعدة مشاريع سابقة:
  - نظام فهرسة وبحث
  - إضافة تلقائية لكل مشروع جديد
- [ ] Similarity Report Generator
- [ ] كتابة Tests

#### أسبوع 18: Behavioral Analysis
- [ ] Git History Analyzer:
  - Commit frequency analysis
  - Commit timing analysis
  - Commit size analysis
  - Author consistency check
  - Single-commit detection (🚩)
- [ ] Coding Style Analyzer:
  - Naming convention consistency
  - Indentation consistency
  - Comment style consistency
  - Code organization patterns
  - Style change detection (🚩)
- [ ] Viva vs Code Correlation:
  - مقارنة أداء المناقشة مع جودة الكود
  - High code quality + Low viva = 🚩🚩🚩
- [ ] كتابة Tests

#### أسبوع 19: Authenticity Score
- [ ] Feature Weight Calculator:
  - Code similarity: 30%
  - Git analysis: 20%
  - Style consistency: 15%
  - Viva performance correlation: 25%
  - Report plagiarism: 10%
- [ ] ML Classifier (Random Forest أو XGBoost):
  - تدريب على بيانات مصنّفة (authentic vs plagiarized)
- [ ] Authenticity Score Generator (0-100)
- [ ] Evidence Report Generator (كل علامة مع الدليل)
- [ ] Alert System (تنبيه الدكتور عند score < 50)
- [ ] كتابة Tests

---

### المرحلة 6: Sandbox وتحليل الأداء (أسبوع 20-21)

#### أسبوع 20: Secure Sandbox
- [ ] Docker Sandbox Manager:
  - إنشاء container لكل مشروع
  - Resource limits (CPU: 1 core, RAM: 512MB, Disk: 1GB)
  - Network isolation (لا وصول للإنترنت)
  - Timeout: 5 دقائق
- [ ] Auto-detector للتقنية:
  - يكتشف Python/Node/Java/.NET ويختار الـ base image
- [ ] Build System:
  - pip install, npm install, mvn build, dotnet build
- [ ] Run System:
  - يشغّل المشروع ويتابع حالته
- [ ] Screenshot Capture (Selenium + headless Chrome)
- [ ] Error Capture (stdout, stderr, crash logs)
- [ ] Cleanup (حذف الـ container بعد الانتهاء)
- [ ] كتابة Tests

#### أسبوع 21: Performance Profiler
- [ ] Response Time Measurer:
  - يرسل HTTP requests ويقيس الاستجابة
  - يقيس كل endpoint
- [ ] Memory Profiler:
  - يراقب RSS memory usage
  - يكشف memory leaks (نمو مستمر)
- [ ] CPU Profiler:
  - يراقب CPU usage أثناء العمل
- [ ] Load Tester:
  - يحاكي 10, 50, 100 مستخدم متزامن
  - يقيس degradation
- [ ] Deadlock Detector:
  - يراقب thread states
- [ ] Performance Report Generator
- [ ] Overall Performance Score Calculator
- [ ] كتابة Tests

---

### المرحلة 7: لوحة التحكم والتقارير (أسبوع 22-24)

#### أسبوع 22: Faculty Dashboard
- [ ] Projects List View:
  - جدول بكل المشاريع مع الحالة
  - فلترة: مادة، دفعة، حالة، نوع
  - بحث بالاسم أو العنوان
  - ترتيب حسب أي عمود
- [ ] Project Detail View:
  - ملخص كل التحليلات
  - الدرجة المقترحة
  - الأعلام والتنبيهات
  - روابط سريعة لكل تحليل
- [ ] Student Comparison View:
  - رسوم بيانية: Radar chart لكل طالب
  - مقارنة جنب-لجنب
  - ترتيب حسب المعيار
- [ ] Alerts Panel:
  - غش مكتشف
  - مشاريع لا تعمل
  - تشابه عالي بين مشاريع
  - مشاريع لم تُحلّل بعد
- [ ] Settings:
  - تعديل أوزان التقييم
  - تعديل العتبات (thresholds)
  - إدارة المواد والطلاب

#### أسبوع 23: Auto-Generated Reports
- [ ] Student Report Template (PDF):
  - ملخص تنفيذي
  - تحليل الكود مع charts
  - تحليل قاعدة البيانات مع ER Diagram
  - تحليل الأمان مع severity chart
  - تحليل التقرير
  - ملخص المناقشة
  - تقرير الأصالة
  - تحليل الأداء
  - الدرجة المقترحة مع التبرير
  - توصيات للتحسين
- [ ] PDF Generator (WeasyPrint أو ReportLab)
- [ ] Excel Exporter (openpyxl):
  - sheet لكل مادة
  - كل المعايير والدرجات
  - charts مدمجة
- [ ] Batch Report Generator (كل المشاريع دفعة واحدة)

#### أسبوع 24: Analytics Dashboard
- [ ] Department Statistics:
  - أكثر 10 أخطاء شيوعاً (Bar chart)
  - متوسط جودة الكود لكل دفعة (Line chart)
  - توزيع الدرجات (Histogram / Bell curve)
  - اللغات والتقنيات الأكثر استخداماً (Pie chart)
  - نسبة الغش المكتشفة (Gauge)
- [ ] Trend Analysis:
  - مقارنة بين الفصول الدراسية
  - هل المستوى يتحسّن؟
  - أنماط الأخطاء المتكررة
- [ ] Interactive Charts (D3.js / Chart.js)
- [ ] Data Export (CSV, JSON)

---

### المرحلة 8: التعلم المستمر (أسبوع 25-26)

#### أسبوع 25: Feedback Learning Loop
- [ ] Grade Adjustment Tracker:
  - يسجّل كل تعديل يعمله الدكتور
  - يحلل الأنماط: أين النظام يخطئ أكثر؟
- [ ] Weight Optimizer:
  - يعدّل أوزان التقييم بناءً على تعديلات الدكاترة
  - Gradient-based optimization
- [ ] Question Quality Improver:
  - يتعلم أي نوع أسئلة أفضل في كشف الفهم
  - يزيد من هذا النوع
- [ ] Fraud Pattern Learner:
  - يتعلم أنماط غش جديدة من الحالات المكتشفة
  - يحدّث القواعد تلقائياً

#### أسبوع 26: Knowledge Base + Model Fine-tuning
- [ ] Project Knowledge Base:
  - فهرسة كل مشروع تم تحليله
  - بحث سريع بالتقنية، اللغة، الأنماط
  - Statistics aggregation
- [ ] Fine-tuning Pipeline:
  - جمع بيانات: أسئلة ← إجابات ← تقييم
  - Fine-tune الـ LLM على هذه البيانات
  - A/B Testing framework
  - Model versioning
- [ ] Automated Retraining Schedule (شهرياً)

---

### المرحلة 9: الاختبار والنشر (أسبوع 27-30)

#### أسبوع 27: Testing Phase 1
- [ ] Unit Tests لكل موديول (pytest):
  - Coverage target: 80%+
  - كل Analyzer
  - كل API endpoint
  - كل utility function
- [ ] Integration Tests:
  - Code Analysis → Knowledge Graph
  - Project Upload → Full Analysis Pipeline
  - Viva Start → Question → Answer → Evaluation
  - Full Grading Pipeline
- [ ] API Tests (httpx + pytest):
  - كل endpoint مع cases مختلفة
  - Error handling
  - Authentication/Authorization

#### أسبوع 28: Testing Phase 2
- [ ] تجربة على 50 مشروع حقيقي:
  - جمع 50 مشروع من دفعات سابقة
  - تشغيل التحليل الكامل
  - مقارنة النتائج مع تقييم الدكتور الفعلي
- [ ] تجربة المناقشة مع 20 طالب متطوع:
  - كل طالب يناقش مشروعه مع النظام
  - جمع Feedback
  - قياس رضا الطلاب
- [ ] Security Testing:
  - OWASP Top 10 على النظام نفسه
  - Penetration testing
  - Authentication bypass attempts
- [ ] Load Testing:
  - 50 تحليل متزامن
  - 20 مناقشة متزامنة
  - Measure response times under load
- [ ] User Acceptance Testing مع 3 دكاترة

#### أسبوع 29: Documentation
- [ ] التقرير النهائي (100-150 صفحة):
  - Chapter 1: Introduction & Problem Statement
  - Chapter 2: Literature Review
  - Chapter 3: System Analysis & Design
  - Chapter 4: Implementation
  - Chapter 5: Testing & Results
  - Chapter 6: Conclusion & Future Work
  - References
  - Appendices
- [ ] API Documentation (Swagger/OpenAPI)
- [ ] User Manual للدكتور (20 صفحة)
- [ ] User Manual للطالب (10 صفحات)
- [ ] Technical Documentation (للمطورين)
- [ ] Installation Guide
- [ ] فيديو Demo (5-10 دقائق)
- [ ] عرض PowerPoint للمناقشة (30-40 شريحة)

#### أسبوع 30: Deployment
- [ ] Production Server Setup:
  - Docker images لكل خدمة
  - Kubernetes deployment files
  - SSL Certificate (Let's Encrypt)
  - Domain configuration
- [ ] Monitoring:
  - Prometheus metrics لكل خدمة
  - Grafana dashboards
  - Alert rules (CPU > 80%, Memory > 90%, etc.)
- [ ] Logging:
  - ELK Stack (Elasticsearch + Logstash + Kibana)
  - Centralized logging لكل الخدمات
- [ ] Backup:
  - Daily automated backup (PostgreSQL, MongoDB, Neo4j)
  - Backup to S3-compatible storage
  - Backup restoration testing
- [ ] Security Hardening:
  - Firewall rules
  - Rate limiting
  - CORS configuration
  - Security headers

---

## 7. هيكل المشروع (Project Structure)

```
ai-project-examiner/
│
├── docker-compose.yml
├── docker-compose.prod.yml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── cd.yml
│       └── security-scan.yml
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── common/
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── Loading.tsx
│   │   │   │   └── ErrorBoundary.tsx
│   │   │   ├── dashboard/
│   │   │   │   ├── ProjectsList.tsx
│   │   │   │   ├── ProjectCard.tsx
│   │   │   │   ├── AlertsPanel.tsx
│   │   │   │   ├── StatsOverview.tsx
│   │   │   │   └── ComparisonView.tsx
│   │   │   ├── analysis/
│   │   │   │   ├── CodeAnalysisView.tsx
│   │   │   │   ├── SecurityView.tsx
│   │   │   │   ├── DatabaseView.tsx
│   │   │   │   ├── ReportView.tsx
│   │   │   │   ├── KnowledgeGraph.tsx
│   │   │   │   └── ERDiagram.tsx
│   │   │   ├── viva/
│   │   │   │   ├── VivaSession.tsx
│   │   │   │   ├── ChatPanel.tsx
│   │   │   │   ├── CodeViewer.tsx
│   │   │   │   ├── VoiceControls.tsx
│   │   │   │   ├── QuestionDisplay.tsx
│   │   │   │   └── VivaResults.tsx
│   │   │   ├── fraud/
│   │   │   │   ├── FraudReport.tsx
│   │   │   │   ├── SimilarityView.tsx
│   │   │   │   └── GitAnalysis.tsx
│   │   │   ├── reports/
│   │   │   │   ├── StudentReport.tsx
│   │   │   │   ├── CourseReport.tsx
│   │   │   │   └── AnalyticsDashboard.tsx
│   │   │   └── grading/
│   │   │       ├── GradeEditor.tsx
│   │   │       ├── CriteriaSettings.tsx
│   │   │       └── GradeSheet.tsx
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── ProjectDetailPage.tsx
│   │   │   ├── VivaPage.tsx
│   │   │   ├── ReportsPage.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   └── StudentPortalPage.tsx
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── types/
│   │   └── i18n/
│   │       ├── ar.json
│   │       └── en.json
│   └── tests/
│
├── services/
│   ├── api-gateway/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── middleware/
│   │   │   │   ├── auth.py
│   │   │   │   ├── cors.py
│   │   │   │   └── rate_limit.py
│   │   │   └── routes/
│   │   │       └── proxy.py
│   │   └── tests/
│   │
│   ├── auth-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── models/
│   │   │   │   └── user.py
│   │   │   ├── schemas/
│   │   │   │   └── auth.py
│   │   │   ├── services/
│   │   │   │   ├── auth_service.py
│   │   │   │   └── jwt_service.py
│   │   │   └── routes/
│   │   │       └── auth.py
│   │   └── tests/
│   │
│   ├── project-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── models/
│   │   │   │   ├── project.py
│   │   │   │   └── course.py
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   │   ├── project_service.py
│   │   │   │   ├── file_service.py
│   │   │   │   └── git_service.py
│   │   │   └── routes/
│   │   └── tests/
│   │
│   ├── code-analyzer/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── analyzers/
│   │   │   │   ├── base_analyzer.py
│   │   │   │   ├── python_analyzer.py
│   │   │   │   ├── java_analyzer.py
│   │   │   │   ├── javascript_analyzer.py
│   │   │   │   ├── csharp_analyzer.py
│   │   │   │   └── cpp_analyzer.py
│   │   │   ├── quality/
│   │   │   │   ├── complexity.py
│   │   │   │   ├── duplication.py
│   │   │   │   ├── dead_code.py
│   │   │   │   ├── code_smells.py
│   │   │   │   └── design_patterns.py
│   │   │   ├── security/
│   │   │   │   ├── sql_injection.py
│   │   │   │   ├── xss_detector.py
│   │   │   │   ├── csrf_detector.py
│   │   │   │   ├── secrets_scanner.py
│   │   │   │   └── vulnerability_classifier.py
│   │   │   ├── graph/
│   │   │   │   ├── graph_builder.py
│   │   │   │   └── neo4j_client.py
│   │   │   ├── services/
│   │   │   └── routes/
│   │   └── tests/
│   │
│   ├── db-analyzer/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── parsers/
│   │   │   │   ├── mysql_parser.py
│   │   │   │   ├── postgresql_parser.py
│   │   │   │   ├── sqlite_parser.py
│   │   │   │   └── mongodb_analyzer.py
│   │   │   ├── analyzers/
│   │   │   │   ├── normalization.py
│   │   │   │   ├── key_analyzer.py
│   │   │   │   ├── index_advisor.py
│   │   │   │   ├── query_analyzer.py
│   │   │   │   └── er_generator.py
│   │   │   ├── services/
│   │   │   └── routes/
│   │   └── tests/
│   │
│   ├── report-analyzer/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── parsers/
│   │   │   │   ├── pdf_parser.py
│   │   │   │   └── docx_parser.py
│   │   │   ├── analyzers/
│   │   │   │   ├── plagiarism_detector.py
│   │   │   │   ├── consistency_checker.py
│   │   │   │   └── documentation_quality.py
│   │   │   ├── services/
│   │   │   └── routes/
│   │   └── tests/
│   │
│   ├── viva-engine/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── generators/
│   │   │   │   ├── question_generator.py
│   │   │   │   ├── context_builder.py
│   │   │   │   └── templates/
│   │   │   │       ├── understanding.json
│   │   │   │       ├── technical.json
│   │   │   │       ├── challenge.json
│   │   │   │       └── verification.json
│   │   │   ├── evaluators/
│   │   │   │   ├── answer_evaluator.py
│   │   │   │   ├── confidence_scorer.py
│   │   │   │   └── evasion_detector.py
│   │   │   ├── dialogue/
│   │   │   │   ├── dialogue_manager.py
│   │   │   │   ├── adaptive_controller.py
│   │   │   │   └── session_manager.py
│   │   │   ├── voice/
│   │   │   │   ├── stt_service.py  # Whisper
│   │   │   │   └── tts_service.py  # Coqui/gTTS
│   │   │   ├── rag/
│   │   │   │   ├── embedder.py
│   │   │   │   ├── retriever.py
│   │   │   │   └── chroma_client.py
│   │   │   ├── services/
│   │   │   └── routes/
│   │   └── tests/
│   │
│   ├── fraud-detector/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── comparators/
│   │   │   │   ├── token_comparator.py
│   │   │   │   ├── ast_comparator.py
│   │   │   │   └── semantic_comparator.py
│   │   │   ├── analyzers/
│   │   │   │   ├── git_analyzer.py
│   │   │   │   ├── style_analyzer.py
│   │   │   │   └── viva_correlation.py
│   │   │   ├── scoring/
│   │   │   │   ├── authenticity_scorer.py
│   │   │   │   └── ml_classifier.py
│   │   │   ├── services/
│   │   │   └── routes/
│   │   └── tests/
│   │
│   ├── sandbox-runner/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── sandbox/
│   │   │   │   ├── docker_manager.py
│   │   │   │   ├── build_system.py
│   │   │   │   └── screenshot_capture.py
│   │   │   ├── profiler/
│   │   │   │   ├── response_time.py
│   │   │   │   ├── memory_profiler.py
│   │   │   │   ├── cpu_profiler.py
│   │   │   │   ├── load_tester.py
│   │   │   │   └── deadlock_detector.py
│   │   │   ├── services/
│   │   │   └── routes/
│   │   └── tests/
│   │
│   └── report-generator/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── app/
│       │   ├── main.py
│       │   ├── generators/
│       │   │   ├── pdf_generator.py
│       │   │   ├── excel_generator.py
│       │   │   └── chart_generator.py
│       │   ├── templates/
│       │   │   ├── student_report.html
│       │   │   └── course_report.html
│       │   ├── services/
│       │   └── routes/
│       └── tests/
│
├── shared/
│   ├── models/
│   │   └── common.py
│   ├── schemas/
│   │   └── events.py
│   ├── utils/
│   │   ├── logger.py
│   │   ├── exceptions.py
│   │   └── validators.py
│   └── config/
│       └── settings.py
│
├── infrastructure/
│   ├── kubernetes/
│   │   ├── namespace.yml
│   │   ├── deployments/
│   │   ├── services/
│   │   ├── configmaps/
│   │   └── secrets/
│   ├── nginx/
│   │   └── nginx.conf
│   ├── monitoring/
│   │   ├── prometheus.yml
│   │   └── grafana/
│   │       └── dashboards/
│   └── scripts/
│       ├── setup.sh
│       ├── backup.sh
│       └── restore.sh
│
├── ml-models/
│   ├── question_generator/
│   ├── answer_evaluator/
│   ├── fraud_classifier/
│   └── training_scripts/
│
├── docs/
│   ├── SRS.md
│   ├── API.md
│   ├── architecture.md
│   ├── user-manual-faculty.md
│   ├── user-manual-student.md
│   └── installation.md
│
├── scripts/
│   ├── seed_data.py
│   ├── generate_test_projects.py
│   └── benchmark.py
│
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

---

## 8. معايير التقييم الافتراضية (Default Grading Criteria)

| المعيار | الوزن | الوصف |
|---------|-------|-------|
| جودة الكود | 20% | بنية، تعقيد، أنماط، نظافة |
| الأمان | 10% | ثغرات، حماية، تشفير |
| قاعدة البيانات | 10% | تصميم، تطبيع، أداء الاستعلامات |
| التقرير | 15% | توثيق، أصالة، تطابق مع الكود |
| المناقشة | 25% | فهم، إجابات تقنية، عمق |
| أصالة المشروع | 10% | عدم الغش، أصالة الكود |
| الأداء | 10% | سرعة، استقرار، تحمّل الضغط |
| **المجموع** | **100%** | |

---

## 9. المخاطر وخطة التخفيف (Risk Management)

| المخاطر | الاحتمال | التأثير | خطة التخفيف |
|---------|----------|---------|-------------|
| LLM يولّد أسئلة غير منطقية | متوسط | عالي | فلترة + مراجعة الدكتور + تحسين مستمر |
| تحليل الكود يفشل مع لغات معينة | متوسط | متوسط | بدء بلغتين ثم التوسع تدريجياً |
| Sandbox غير آمن | منخفض | عالي جداً | عزل كامل + resource limits + security audit |
| أداء بطيء مع مشاريع كبيرة | متوسط | متوسط | تقسيم التحليل + caching + async processing |
| الطلاب يتحايلون على كشف الغش | متوسط | متوسط | طبقات متعددة + تعلم مستمر |
| نقص البيانات للتدريب | عالي | متوسط | بدء بقواعد ثم تجميع بيانات تدريجياً |
| تعقيد المشروع يتجاوز الوقت | عالي | عالي | تقسيم لأولويات + MVP أولاً |

---

## 10. النسخة الأولية (MVP - Minimum Viable Product)

إذا الوقت ضاغط، ابدأ بـ MVP يشمل:

### الأولوية 1 (إلزامي — 12 أسبوع):
1. ✅ رفع المشاريع (كود + تقرير)
2. ✅ تحليل الكود (AST + Quality + Security) — لغتين فقط (Python + Java)
3. ✅ تحليل قاعدة البيانات (MySQL فقط)
4. ✅ المناقشة الذكية (نصية فقط، إنجليزي)
5. ✅ تقرير بسيط للدكتور
6. ✅ لوحة تحكم أساسية

### الأولوية 2 (مهم — 6 أسابيع إضافية):
7. كشف الغش (Token-based + Git analysis)
8. تحليل التقرير (الانتحال)
9. دعم العربية في المناقشة
10. تصدير PDF

### الأولوية 3 (متقدم — 6 أسابيع إضافية):
11. Voice interface
12. Sandbox + Performance profiling
13. Analytics Dashboard
14. التعلم المستمر
15. باقي اللغات البرمجية

---

## 11. مراجع ومصادر مقترحة (References)

### أوراق بحثية:
1. "Automated Assessment of Programming Assignments" - IEEE, 2023
2. "Code Clone Detection: A Systematic Review" - ACM Computing Surveys
3. "Adaptive Testing with AI" - Educational Technology Research
4. "AST-based Code Analysis" - Software Engineering Conference
5. "RAG for Domain-Specific Question Generation" - NLP Conference
6. "Plagiarism Detection in Arabic Text" - Arabic NLP Workshop

### أدوات وتقنيات:
- Tree-sitter: https://tree-sitter.github.io/
- Semgrep: https://semgrep.dev/
- LangChain: https://langchain.com/
- ChromaDB: https://www.trychroma.com/
- Neo4j: https://neo4j.com/
- FastAPI: https://fastapi.tiangolo.com/
- Whisper: https://github.com/openai/whisper

### مشاريع مشابهة للدراسة:
- MOSS (Stanford): https://theory.stanford.edu/~aiken/moss/
- CodeGrade: https://www.codegrade.com/
- Codio: https://www.codio.com/
- SonarQube: https://www.sonarqube.org/

---

## 12. الخلاصة

هذا المشروع يمثل نظاماً متكاملاً لتقييم المشاريع البرمجية الجامعية باستخدام
الذكاء الاصطناعي. يجمع بين تحليل الكود العميق، المناقشة التكيّفية، كشف الغش
المتقدم، وتحليل الأداء في منصة واحدة تخدم الدكتور والطالب.

### ما يميّز المشروع:
- **ليس chatbot عادي** — يفهم بنية الكود الفعلية ويسأل عنها
- **متعدد الطبقات** — 8 موديولات متكاملة
- **يحل مشكلة حقيقية** — موجودة في كل جامعة
- **قابل للنشر** — يمكن تحويله لمنتج تجاري (SaaS)
- **بحثي** — يمكن نشر 2-3 أوراق بحثية منه
- **تعليمي** — يغطي AI, NLP, Compilers, Security, Databases, DevOps

### الأرقام المتوقعة:
- 40,000 - 60,000 سطر كود
- 500+ ملف
- 80+ API endpoint
- 8 خدمات مصغرة
- 100-150 صفحة تقرير
- 7-8 أشهر تطوير

---

*تم إعداد هذه الخطة في: نوفمبر 2026*
*المشروع: AI Project Examiner*
*الجامعة: جامعة صنعاء — كلية الحاسوب وتكنولوجيا المعلومات*
