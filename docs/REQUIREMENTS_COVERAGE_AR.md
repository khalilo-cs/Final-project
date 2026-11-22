# تغطية متطلبات الخطة — مِحَكّ

مطابقة كل متطلب في [`PROJECT_PLAN.md`](PROJECT_PLAN.md) بمكانه في الكود وبالاختبار الذي يثبته.

**الحالة:** ✅ منفّذ ومختبر آلياً · 🟡 منفّذ مع حدّ مذكور · ⬜ غير منفّذ

**آخر تحقق:** 22 نوفمبر 2026. نجحت **376 اختباراً آلياً** في 11 مجموعة (`make test`)، والكود قرابة 20,800 سطر Python و3,400 سطر TypeScript.

---

## 1. المتطلبات الوظيفية

### FR-01 إدارة المستخدمين
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 01.1 | ثلاثة أدوار (Admin/Faculty/Student) | ✅ | `auth-service/app/models/user.py` |
| 01.2 | إدارة الصلاحيات | ✅ | `PUT/DELETE /users/{id}` مع حماية آخر مدير — `tests/test_user_admin.py` |
| 01.3 | ربط الطلاب بالمواد والدكاترة | ✅ | `project-service/app/routes/courses.py` |
| 01.4 | الدخول بحساب الجامعة (LDAP/OAuth) | ✅ | OIDC: `services/oidc.py`، LDAP/AD: `services/ldap_auth.py` — `tests/test_oidc.py` و`tests/test_ldap.py` |

### FR-02 رفع المشاريع
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 02.1 | رفع الكود (ZIP أو رابط Git) | ✅ | رفع مجزأ قابل للاستئناف + `services/git_import.py` — `tests/test_uploads.py` و`tests/test_git_import.py` |
| 02.2 | التقرير (PDF/DOCX) | ✅ | `routes/projects.py` |
| 02.3 | قاعدة البيانات (SQL dump/Schema) | ✅ | SQL و MongoDB JSON |
| 02.4 | تحديد اللغات | ✅ | حقل `programming_languages` + كشف تلقائي |
| 02.5 | تحديد التقنيات والأطر | ✅ | حقل `frameworks` + `code-analyzer/app/analyzers/technologies.py` |
| 02.6 | رابط مستودع Git | ✅ | يُستنسخ مع تاريخه (hosts مسموحة فقط، ضد SSRF) |

### FR-03 تحليل الكود
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 03.1 | AST لكل ملف | ✅ | `code-analyzer/app/analyzers/*` (tree-sitter + Python ast) |
| 03.2 | Knowledge Graph | ✅ | `app/graph/` + تصدير Cypher لـ Neo4j: `GET /analysis/code/{id}/graph.cypher` |
| 03.3 | Cyclomatic + Cognitive | ✅ | `app/quality/` |
| 03.4 | Code Smells | ✅ | دوال طويلة، تكرار، God Class، تداخل عميق، استعلام داخل حلقة (N+1) |
| 03.5 | Design Patterns | ✅ | `app/graph/analysis.py` |
| 03.6 | SOLID | ✅ | `app/graph/analysis.py` — `tests/test_graph.py` |
| 03.7 | Dead Code | ✅ | `app/quality/dead_code.py` |
| 03.8 | التبعيات | ✅ | الاعتماد الدائري، الترابط، عدم الاستقرار |
| 03.9 | Python, Java, C++, C#, JS/TS | ✅ | + PHP في الأمان |

### FR-04 تحليل الأمان
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 04.1 | SQL Injection | ✅ | `app/security/*_rules.py` |
| 04.2 | XSS | ✅ | |
| 04.3 | CSRF | ✅ | `app/security/web_rules.py`: Django وFlask وExpress وSpring وASP.NET وPHP — `tests/test_web_rules.py` |
| 04.4 | Hardcoded Secrets | ✅ | `secrets_scanner.py` |
| 04.5 | Insecure Deserialization | ✅ | |
| 04.6 | Path Traversal | ✅ | Python (تتبع مدخلات الطلب)، Java، JS، C#، PHP |
| 04.7 | Command Injection | ✅ | |
| 04.8 | Missing Input Validation | ✅ | `web_rules.py` + `python_rules.py` |
| 04.9 | تصنيف الخطورة | ✅ | Critical/High/Medium/Low، والثغرة الحرجة تحدّ الدرجة المقترحة عند 79 |

### FR-05 تحليل قاعدة البيانات
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 05.1 | MySQL, PostgreSQL, SQLite, MongoDB | ✅ | `parsers/schema_parser.py` + `parsers/mongo_parser.py` — `tests/test_mongo.py` |
| 05.2 | التطبيع 1NF → BCNF | 🟡 | `analyzers/normalization.py`. تقدير من الأسماء والمفاتيح، لأن الاعتماديات الوظيفية لا تُثبت من الـ schema وحده |
| 05.3 | مفاتيح مفقودة | ✅ | `key_analyzer.py` |
| 05.4 | علاقات خاطئة/مفقودة | ✅ | |
| 05.5 | N+1، فهارس مفقودة، SELECT * | ✅ | N+1 يُكشف من الكود (استعلام داخل حلقة) |
| 05.6 | ER Diagram | ✅ | Mermaid |
| 05.7 | مقارنة الـ Schema بالتقرير | ✅ | `report-analyzer/app/analyzers/consistency.py`: عدد الجداول وأسماؤها |

### FR-06 تحليل التقرير
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 06.1 | استخراج النص | ✅ | pypdf و python-docx |
| 06.2 | الانتحال عربي + إنجليزي | ✅ | Winnowing مع توحيد النص العربي |
| 06.3 | مقارنة التقرير بالكود | ✅ | |
| 06.4 | كشف التناقضات | ✅ | |
| 06.5 | التحقق من UML | 🟡 | أسماء الكلاسات في مخطط الفئات تُقارن بالكود. المخطط المرسوم كصورة لا يُقرأ (لا OCR) |
| 06.6 | جودة التوثيق | ✅ | `analyzers/documentation.py` |

### FR-07 المناقشة الذكية
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 07.1 | أسئلة من الكود الفعلي | ✅ | `viva-engine/app/providers/` |
| 07.2–07.3 | مستويات متدرجة وتكيّف | ✅ | `engine/dialogue.py` |
| 07.4 | Confidence Score | ✅ | |
| 07.5 | نصية | ✅ | HTTP + WebSocket `/ws/viva/{id}` — `tests/test_live.py` |
| 07.6 | صوتية (STT + TTS) | ✅ | Whisper على الخادم + قراءة الأسئلة بصوت في المتصفح |
| 07.7 | عربي وإنجليزي | ✅ | |
| 07.8 | تسجيل الجلسة | ✅ | `/transcript` و`/results` |
| 07.9 | عرض الكود مع تحديد الأسطر | ✅ | `frontend/src/components/CodeView.tsx` بأرقام أسطر الملف الحقيقية |

### FR-08 كشف الغش
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 08.1 | Token-based | ✅ | `fraud-detector/app/analyzers/similarity.py` |
| 08.2 | AST-based | ✅ | أشكال الدوال بعد حذف الأسماء |
| 08.3 | Semantic-based | ✅ | `semantic.py` + رأي ثانٍ اختياري بالتضمين (embeddings) |
| 08.4 | مقارنة بالدفعات السابقة | ✅ | فهرس دائم، ويُراعى ترتيب التسليم |
| 08.5 | تحليل Git History | ✅ | `git_history.py` |
| 08.6 | اتساق الأسلوب | ✅ | `style.py` |
| 08.7 | أداء المناقشة مقابل جودة الكود | ✅ | فجوة المناقشة في `authenticity.py` |
| 08.8 | Authenticity Score | ✅ | + بصمة الفهم (ابتكار إضافي) |

### FR-09 Sandbox والأداء
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 09.1 | Docker معزول | 🟡 | `sandbox-runner` بلا شبكة وبحدود للموارد. يحتاج Docker، فلم يُختبر هنا إلا بمحاكاة |
| 09.2–09.4 | Response Time، Memory، CPU | ✅ | `profiler/http_profiler.py` |
| 09.5 | Load Testing | ✅ | 1 ثم 10 ثم 50 مستخدماً |
| 09.6 | Memory Leaks | 🟡 | قرينة: ذاكرة تزيد مع كل جولة ضغط |
| 09.7 | Deadlocks | 🟡 | قرينة: معظم الطلبات بلا رد مع بقاء العملية حية |
| 09.8 | Screenshots | ✅ | `profiler/screenshots.py` (Chromium، وكل طلب خارج المشروع محجوب) — `tests/test_screenshots.py` |

### FR-10 لوحة الدكتور
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 10.1 | كل المشاريع | ✅ | |
| 10.2 | فلترة: مادة، دفعة، نوع | ✅ | `FacultyDashboard.tsx` |
| 10.3 | مقارنة الطلاب بيانياً | ✅ | `components/CompareStudents.tsx` |
| 10.4 | PDF لكل طالب | ✅ | `report-generator` |
| 10.5 | Excel | ✅ | |
| 10.6 | تنبيهات | ✅ | غش، مشاريع لا تعمل، مجموعات نسخ |
| 10.7 | تعديل الأوزان | ✅ | |
| 10.8 | درجة مقترحة مع تبرير | ✅ | |

### FR-11 التقارير والإحصائيات
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 11.1–11.6 | تقرير شامل، إحصائيات القسم، الأخطاء الشائعة، التوزيع، مقارنة الفصول، الاتجاهات | ✅ | `routes/dashboard.py` + `AnalyticsPage.tsx` + `/reports/*` |

### FR-12 التعلم المستمر
| | المتطلب | الحالة | أين |
|---|---|---|---|
| 12.1 | التعلم من تعديلات الدكتور | ✅ | `LearningLog` + مراجعة إجابات المناقشة |
| 12.2 | تحسين الأوزان تلقائياً | ✅ | `services/learning.py`: أوزان تطابق الدرجات المعتمدة — `tests/test_learning.py` |
| 12.3 | تحسين توليد الأسئلة | ✅ | تعلّم ذاتي في viva-engine وقوة تمييز كل سؤال |
| 12.4 | أنماط غش جديدة | ✅ | مجموعات النسخ (3 مشاريع مترابطة أو أكثر) + إعادة الصياغة + بصمة الفهم |
| 12.5 | Knowledge Base من المشاريع | ✅ | `viva-engine/app/knowledge/` |

---

## 2. المتطلبات غير الوظيفية

| | المتطلب | الحالة | كيف |
|---|---|---|---|
| NFR-01 | تحليل 10,000 سطر في أقل من 5 دقائق، ومناقشة تستجيب في أقل من 3 ثوانٍ | ✅ | مقيس: 3–4 ثوانٍ للتحليل و 0.01 ثانية للإجابة ([`tools/local-stack`](../tools/local-stack/README.md)) |
| NFR-01 | 50 تحليلاً و20 مناقشة متزامنة | ✅ | مقيس: 50 مشروعاً متزامناً كلها نجحت في 38 ثانية، و20 مناقشة متزامنة 95% من إجاباتها أقل من 1.03 ثانية. على 4 أنوية مع SQLite |
| NFR-02 | HTTPS/TLS | ✅ | `nginx-tls.conf` + `docker-compose.tls.yml`، مع تحويل HTTP→HTTPS و HSTS. جُرّب بـ nginx حقيقي |
| NFR-02 | AES-256 للبيانات المخزنة | ✅ | `services/crypto_store.py`: AES-256-GCM لملفات الطلاب. قاعدة البيانات تُحمى بتشفير القرص |
| NFR-02 | Sandbox بلا شبكة | ✅ | |
| NFR-02 | Rate Limiting | ✅ | nginx + قفل الحساب بعد محاولات فاشلة |
| NFR-02 | RBAC | ✅ | |
| NFR-02 | Audit Log | ✅ | `app/audit.py` في خدمتَي المشاريع والمصادقة — `tests/test_audit.py` |
| NFR-03 | Microservices | ✅ | 10 خدمات + بوابة |
| NFR-03 | توسع أفقي | ✅ | الخدمات بلا حالة في الذاكرة، والمهام تُحجز ذرّياً |
| NFR-03 | Message Queue | ✅ | طابور دائم في PostgreSQL (`services/jobs.py`) بدل RabbitMQ — `tests/test_jobs.py` |
| NFR-03 | Caching | ✅ | `code-analyzer/app/services/result_cache.py` |
| NFR-04 | عربية بالكامل مع الإنجليزية | ✅ | `frontend/src/i18n.ts`. النصوص القادمة من الخادم تبقى بلغتها |
| NFR-04 | متجاوبة | ✅ | |
| NFR-04 | توثيق ودليل مستخدم | ✅ | `README.md` + [`USER_GUIDE_AR.md`](USER_GUIDE_AR.md) |
| NFR-05 | Uptime 99% | 🟡 | `restart: unless-stopped` و healthchecks، ومهام تُستأنف بعد انقطاع الكهرباء. نسبة التوفر تُقاس في التشغيل الفعلي |
| NFR-05 | نسخ احتياطي يومي | ✅ | خدمة `backup` — جُرّبت مع PostgreSQL 16 حقيقي |
| NFR-05 | استرجاع في أقل من ساعة | ✅ | `tools/backup/restore.sh` مع التحقق من checksums |
| NFR-05 | معالجة الأخطاء | ✅ | كل خدمة تفشل بلطف ولا توقف بقية التحليل |

---

## 3. الـ APIs (القسم 4.4)

كل مسارات الخطة موجودة بالأسماء نفسها، ومنها التي أضيفت في هذه المرحلة:

- `PUT/DELETE /users/{id}`
- `POST /analysis/security/{id}`
- `POST /fraud/analyze/{id}` و `GET /fraud/{id}/similar-projects`
- `GET /viva/{id}/next-question` و `/results` و `WS /ws/viva/{id}`
- `GET /sandbox/{id}/status` و `/screenshots`
- `GET /reports/student/{id}` و `/reports/course/{id}` و `/reports/analytics/department`
- `GET /dashboard/admin/stats`

---

## 4. تقنيات استُبدلت عن الخطة ولماذا

| في الخطة | المستخدم | السبب |
|---|---|---|
| RabbitMQ / Celery | طابور دائم في PostgreSQL | خدمة أقل تُدار وتنقطع. المهام تبقى بعد انقطاع الكهرباء وتُحجز ذرّياً |
| Neo4j | NetworkX + تصدير Cypher | لا يحتاج خادماً إضافياً، ويمكن تحميل الخريطة في Neo4j عند الحاجة |
| ChromaDB / LangChain | BM25 + تضمين اختياري + مزودات مباشرة | أخف وأوضح، ويعمل بلا إنترنت |
| MongoDB للسجلات | PostgreSQL (JSON) | قاعدة واحدة أسهل للنسخ الاحتياطي. ودعم MongoDB موجود كقاعدة تُحلَّل من مشاريع الطلاب |
| Socket.io | WebSocket أصلي + HTTP مع heartbeat | HTTP أصمد على الاتصال الضعيف، والمقبس متاح للمناقشة الحية |
| i18next | قاموس مع مترجم للواجهة | ترجمة بلا إعادة كتابة كل المكونات |
| Monaco Editor | `CodeView` بأرقام الأسطر | عرض فقط، بلا حمل محرر كامل (حوالي 3MB) على اتصال ضعيف |
| Semgrep / PMD / ESLint | قواعد خاصة على AST | تعمل بلا إنترنت، وبرسائل عربية، وبإصلاحات مقترحة |
| MinIO | ملفات محلية مشفرة AES-256 | لا خادم إضافياً، والتشفير داخل التطبيق |
| Kubernetes | Docker Compose | خادم واحد يكفي للكلية. الخدمات قابلة للنقل إلى K8s لاحقاً |
| Prometheus / Grafana / ELK | Audit log + `admin/stats` + healthchecks | يكفي لحجم الكلية. المراقبة الكاملة من التطوير المستقبلي |

---

## 5. ما بقي (يحتاج بيئة الكلية)

1. تشغيل `docker compose up` كاملاً على خادم الكلية، واختبار Sandbox بمشاريع حقيقية.
   النظام كله يعمل الآن بدون Docker عبر `tools/local-stack/run.sh`، ونجح عليه اختبار المتصفح الكامل (`e2e.py`).
2. إعادة قياس الأداء على الخادم الفعلي مع PostgreSQL ونموذج لغوي محلي.
3. التجربة الميدانية ومقارنة درجات النظام بلجنة بشرية ([`EVALUATION_PROTOCOL_AR.md`](EVALUATION_PROTOCOL_AR.md)).
4. إشعارات SMS، وهي ليست من متطلبات الخطة.
