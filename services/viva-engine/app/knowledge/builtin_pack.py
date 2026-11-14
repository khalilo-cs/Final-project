"""Built-in knowledge pack, loaded automatically at startup.

Written for this project (by the Claude Code assistant that built it) so the system
starts with real knowledge before any project, model or professor has taught it
anything. Topics use the same keys the auto-learner derives from projects:
    vuln:<type>  db:<area>  tech:<name>  arch:<pattern>  code:<area>
Each topic: explanation (ar/en), key points used to grade answers, viva questions.
"""

PACK_VERSION = 1

TOPICS: dict[str, dict] = {
    "vuln:sql_injection": {
        "title": "SQL Injection",
        "ar": "حقن SQL يحدث عندما تُدمج مدخلات المستخدم داخل نص الاستعلام، فيستطيع المهاجم تغيير "
        "معنى الاستعلام (مثل ' OR 1=1 --) لقراءة أو حذف بيانات. الحل هو الاستعلامات المُعدّة "
        "(Prepared/Parameterized Statements) حيث تُرسل القيم منفصلة عن نص SQL ولا تُفسَّر ككود.",
        "en": "SQL injection happens when user input is concatenated into SQL text, letting an "
        "attacker change the query (e.g. ' OR 1=1 --). Prepared statements send values "
        "separately, so they are never parsed as SQL.",
        "points": [
            "prepared statement",
            "parameter",
            "placeholder",
            "?",
            "concatenation",
            "' or 1=1",
            "escape",
            "orm",
        ],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "اشرح كيف يمكن لمهاجم استغلال حقن SQL في نموذج تسجيل الدخول، "
                "وما الفرق بين الاستعلام المُعدّ ومجرد تنظيف المدخلات؟",
                ["prepared", "parameter", "or 1=1", "escape"],
            ),
            (
                "ar",
                "technical",
                2,
                "لماذا لا يكفي استخدام replace لحذف علامات الاقتباس لمنع حقن SQL؟",
                ["encoding", "prepared", "parameter", "bypass"],
            ),
            (
                "en",
                "challenge",
                3,
                "How would an attacker exploit SQL injection in a search box, "
                "and why do prepared statements stop it?",
                ["prepared", "parameter", "union", "data"],
            ),
        ],
    },
    "vuln:xss": {
        "title": "Cross-Site Scripting (XSS)",
        "ar": "XSS يحدث عند عرض مدخلات المستخدم في صفحة HTML دون ترميز، فيُنفّذ المتصفح JavaScript "
        "كتبه المهاجم ويسرق الجلسات أو يغيّر الصفحة. الحل: ترميز المخرجات حسب السياق (HTML/JS/URL)، "
        "وسياسة CSP، وعلامة HttpOnly على ملفات تعريف الجلسة.",
        "en": "XSS happens when user input is written to HTML without encoding, so the browser "
        "runs attacker JavaScript. Fix: context-aware output encoding, CSP, HttpOnly cookies.",
        "points": ["encode", "escape", "csp", "httponly", "stored", "reflected", "script"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "ما الفرق بين XSS المخزّن والمنعكس؟ وأين يمكن أن يظهر كل منهما في مشروعك؟",
                ["stored", "reflected", "database", "url"],
            ),
            (
                "ar",
                "technical",
                2,
                "كيف تمنع XSS عند عرض اسم المستخدم في الصفحة؟",
                ["encode", "escape", "template", "csp"],
            ),
        ],
    },
    "vuln:command_injection": {
        "title": "Command Injection",
        "ar": "حقن الأوامر يحدث عند تمرير مدخلات المستخدم إلى shell (مثل os.system أو Runtime.exec "
        "بنص واحد)، فيضيف المهاجم أوامر مثل ; rm -rf. الحل: تمرير الأمر كقائمة معاملات بدون shell، "
        "والتحقق من المدخلات بقائمة قيم مسموحة.",
        "en": "Command injection: user input reaches a shell, so ; or && add new commands. Pass "
        "arguments as a list without a shell and validate against an allow-list.",
        "points": ["shell", "argument list", "allow-list", "whitelist", "validate", ";", "&&"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "لماذا يُعدّ subprocess.run مع shell=True خطيراً، وكيف تكتبه بأمان؟",
                ["shell", "list", "arguments", "validate"],
            ),
        ],
    },
    "vuln:path_traversal": {
        "title": "Path Traversal",
        "ar": "اجتياز المسار يحدث عند بناء مسار ملف من مدخلات المستخدم، فيستخدم المهاجم ../ للوصول "
        "لملفات خارج المجلد المقصود. الحل: تطبيع المسار ثم التحقق أنه يبدأ بالمجلد الأساسي، أو "
        "استخدام معرّفات بدل أسماء الملفات.",
        "en": "Path traversal: ../ in user input escapes the intended folder. Normalize the path "
        "and check it stays under the base directory, or use ids instead of file names.",
        "points": ["../", "normalize", "canonical", "base directory", "realpath", "id"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "كيف تمنع طالباً من تنزيل ملفات طالب آخر عبر رابط تنزيل يحتوي اسم الملف؟",
                ["normalize", "base", "authorization", "id"],
            ),
        ],
    },
    "vuln:hardcoded_secret": {
        "title": "Hardcoded Secrets",
        "ar": "كتابة كلمات المرور ومفاتيح API داخل الكود تجعلها مكشوفة لكل من يرى المستودع، وتبقى في "
        "تاريخ Git حتى بعد حذفها. الحل: متغيرات البيئة أو ملف .env خارج Git أو خزنة أسرار، وتغيير "
        "أي سر تسرّب.",
        "en": "Secrets in code are exposed to anyone with the repository and stay in Git history. "
        "Use environment variables, an untracked .env or a secrets vault; rotate leaked ones.",
        "points": ["environment variable", "env", ".env", "gitignore", "rotate", "vault"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "أين يجب أن تُخزّن كلمة مرور قاعدة البيانات في مشروعك، ولماذا لا "
                "يكفي حذفها من الكود بعد رفعه إلى GitHub؟",
                ["env", "history", "rotate", "gitignore"],
            ),
        ],
    },
    "vuln:insecure_deserialization": {
        "title": "Insecure Deserialization",
        "ar": "فك تسلسل بيانات غير موثوقة باستخدام pickle أو ObjectInputStream قد ينفّذ كوداً يختاره "
        "المهاجم. الحل: استخدام صيغ بيانات بسيطة مثل JSON، وعدم فك تسلسل مدخلات المستخدم.",
        "en": "Deserializing untrusted data with pickle or ObjectInputStream can run attacker "
        "code. Use plain data formats like JSON for anything from users.",
        "points": ["json", "pickle", "untrusted", "safe_load", "code execution"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "لماذا يُعدّ pickle.loads على بيانات من المستخدم خطراً؟ وما البديل؟",
                ["code execution", "json", "untrusted"],
            ),
        ],
    },
    "vuln:weak_hash": {
        "title": "Password hashing",
        "ar": "MD5 و SHA-1 سريعة جداً فتُكسر كلمات المرور بها بالتخمين خلال ثوانٍ. لكلمات المرور "
        "تُستخدم خوارزميات بطيئة مع salt مثل bcrypt أو argon2، ولا تُخزّن كلمة المرور نفسها أبداً.",
        "en": "MD5/SHA-1 are fast, so password hashes are brute-forced quickly. Use slow salted "
        "algorithms (bcrypt, argon2) and never store the password itself.",
        "points": ["bcrypt", "argon2", "salt", "slow", "brute force", "rainbow"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "كيف تخزّن كلمات مرور المستخدمين في نظامك؟ ولماذا لا تستخدم MD5؟",
                ["hash", "bcrypt", "salt", "brute"],
            ),
            (
                "en",
                "technical",
                2,
                "Why is a salt needed when hashing passwords?",
                ["rainbow", "same password", "unique"],
            ),
        ],
    },
    "db:normalization": {
        "title": "Normalization (1NF–3NF)",
        "ar": "التطبيع يزيل التكرار وتناقض البيانات: 1NF قيمة واحدة في كل حقل وبلا أعمدة مكررة، "
        "2NF كل عمود يعتمد على المفتاح كاملاً لا جزء منه، 3NF لا يعتمد عمود على عمود غير مفتاح "
        "(لا تنسخ اسم العميل في جدول الطلبات بل اربط بمعرّفه).",
        "en": "1NF: atomic values, no repeating groups. 2NF: no dependency on part of a "
        "composite key. 3NF: no dependency on non-key columns (no transitive dependencies).",
        "points": [
            "atomic",
            "repeating",
            "partial dependency",
            "transitive",
            "composite key",
            "redundancy",
            "anomaly",
            "1nf",
            "2nf",
            "3nf",
        ],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "ما مستوى التطبيع الذي وصلت إليه قاعدة بياناتك؟ أعطِ مثالاً من جداولك على قاعدة 3NF.",
                ["3nf", "transitive", "foreign key"],
            ),
            (
                "ar",
                "challenge",
                3,
                "ما مشكلة تخزين أكثر من رقم هاتف في حقل واحد مفصولة بفواصل؟ وكيف تصمّمها بشكل صحيح؟",
                ["1nf", "atomic", "table", "foreign key"],
            ),
            (
                "en",
                "challenge",
                3,
                "When could denormalizing a table be a good decision?",
                ["performance", "read", "join", "redundancy"],
            ),
        ],
    },
    "db:keys": {
        "title": "Primary and foreign keys",
        "ar": "المفتاح الأساسي يميّز كل صف ولا يتكرر، والمفتاح الأجنبي يضمن أن المرجع موجود فعلاً "
        "(سلامة المراجع)، ويحدد ما يحدث عند الحذف (CASCADE أو RESTRICT أو SET NULL).",
        "en": "A primary key identifies each row; a foreign key enforces referential integrity "
        "and defines delete behaviour (CASCADE, RESTRICT, SET NULL).",
        "points": ["unique", "referential integrity", "cascade", "restrict", "set null", "orphan"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "ماذا يحدث في قاعدة بياناتك عند حذف سجل مرتبط بسجلات أخرى؟ ولماذا "
                "اخترت هذا السلوك؟",
                ["cascade", "restrict", "foreign key", "orphan"],
            ),
            (
                "ar",
                "verification",
                4,
                "ما المفتاح الأساسي لأهم جدول في مشروعك؟ ولماذا اخترته؟",
                ["primary key", "unique", "auto"],
            ),
        ],
    },
    "db:indexes": {
        "title": "Indexes",
        "ar": "الفهرس يسرّع البحث في عمود على حساب مساحة إضافية وبطء بسيط في الإضافة والتعديل. تُفهرس "
        "الأعمدة المستخدمة في WHERE و JOIN والمفاتيح الأجنبية.",
        "en": "Indexes speed up lookups at the cost of storage and slower writes. Index columns "
        "used in WHERE, JOIN and foreign keys.",
        "points": ["where", "join", "b-tree", "write", "slower insert", "explain"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "أي استعلام في مشروعك سيصبح بطيئاً مع آلاف السجلات؟ وأي فهرس تضيف؟",
                ["index", "where", "join", "explain"],
            ),
        ],
    },
    "arch:mvc": {
        "title": "MVC",
        "ar": "MVC يفصل البيانات ومنطقها (Model) عن العرض (View) عن معالجة الطلبات (Controller)، "
        "فيسهل تعديل الواجهة دون المساس بالمنطق ويسهل الاختبار.",
        "en": "MVC separates data and rules (Model), presentation (View) and request handling "
        "(Controller), so each changes and is tested independently.",
        "points": ["model", "view", "controller", "separation", "request", "responsibility"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "أين يوجد منطق التحقق من البيانات في مشروعك: في Controller أم Model؟ ولماذا؟",
                ["model", "controller", "validation"],
            ),
        ],
    },
    "code:complexity": {
        "title": "Complexity and refactoring",
        "ar": "الدالة كثيرة الشروط (تعقيد دوراني عالٍ) صعبة الفهم والاختبار. تُبسّط باستخراج أجزاء "
        "منها في دوال صغيرة بأسماء واضحة، والإرجاع المبكر، واستبدال سلاسل if بجداول أو تعدد الأشكال.",
        "en": "High cyclomatic complexity makes code hard to test. Extract smaller functions, use "
        "early returns, and replace long if-chains with lookup tables or polymorphism.",
        "points": ["extract", "function", "early return", "single responsibility", "test"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "ما أعقد دالة في مشروعك؟ وكيف تقسمها إلى دوال أصغر؟",
                ["extract", "function", "responsibility"],
            ),
        ],
    },
    "code:testing": {
        "title": "Testing",
        "ar": "اختبارات الوحدة تتحقق من كل دالة منفردة، واختبارات التكامل من تعاون الأجزاء. تكتشف "
        "الأخطاء مبكراً وتسمح بالتعديل بثقة.",
        "en": "Unit tests check single functions, integration tests check parts working "
        "together; they catch regressions and allow safe changes.",
        "points": ["unit test", "integration", "assert", "pytest", "junit", "edge case", "mock"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "كيف اختبرت مشروعك؟ اذكر حالة حدّية (edge case) اختبرتها.",
                ["test", "edge", "case", "assert"],
            ),
        ],
    },
    "general:authentication": {
        "title": "Authentication and sessions",
        "ar": "المصادقة تتحقق من هوية المستخدم والتفويض يحدد صلاحياته. الجلسات تُحفظ بملف تعريف "
        "HttpOnly أو برموز JWT بصلاحية قصيرة، ويجب التحقق من الصلاحية في الخادم لكل طلب.",
        "en": "Authentication proves identity, authorization decides permissions. Use HttpOnly "
        "session cookies or short-lived JWTs and check permissions server-side on every request.",
        "points": [
            "authentication",
            "authorization",
            "session",
            "jwt",
            "httponly",
            "role",
            "server-side",
        ],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "كيف يعرف نظامك أن المستخدم مسجّل دخوله، وكيف تمنع طالباً من فتح صفحة الدكتور؟",
                ["session", "role", "server", "authorization"],
            ),
        ],
    },
    "tech:flask": {
        "title": "Flask",
        "ar": "Flask إطار Python خفيف: تُعرَّف المسارات بـ @app.route، ويُستخدم Jinja2 للقوالب "
        "(يرمّز المخرجات تلقائياً)، وتُضاف القدرات عبر إضافات مثل Flask-Login و SQLAlchemy.",
        "en": "Flask is a lightweight Python framework: routes via @app.route, Jinja2 templates "
        "(auto-escaping), features added through extensions.",
        "points": ["route", "jinja", "request", "blueprint", "extension", "debug"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "كيف يصل طلب HTTP إلى الدالة المناسبة في تطبيق Flask الخاص بك؟",
                ["route", "decorator", "url", "request"],
            ),
        ],
    },
    "tech:django": {
        "title": "Django",
        "ar": "Django إطار Python متكامل: ORM للنماذج، ونظام Migrations، ولوحة إدارة، وحماية CSRF "
        "مدمجة. يتبع نمط MTV (Model-Template-View).",
        "en": "Django: full-stack Python framework with ORM, migrations, admin and built-in CSRF "
        "protection, following MTV.",
        "points": ["orm", "migration", "model", "template", "view", "csrf", "admin"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "ما دور migrations في Django؟ وماذا يحدث لو عدّلت نموذجاً بدونها؟",
                ["migration", "schema", "database", "model"],
            ),
        ],
    },
    "tech:spring": {
        "title": "Spring / Spring Boot",
        "ar": "Spring يعتمد على حقن الاعتماديات (Dependency Injection) حيث ينشئ الإطار الكائنات "
        "ويربطها، وتُعرَّف الطبقات بـ @Controller و @Service و @Repository.",
        "en": "Spring is built on dependency injection; layers are declared with @Controller, "
        "@Service and @Repository.",
        "points": [
            "dependency injection",
            "bean",
            "controller",
            "service",
            "repository",
            "autowired",
            "jpa",
        ],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "ما فائدة حقن الاعتماديات في مشروع Spring الخاص بك؟ أعطِ مثالاً.",
                ["dependency", "injection", "bean", "test"],
            ),
        ],
    },
    "tech:mysql": {
        "title": "MySQL",
        "ar": "MySQL قاعدة بيانات علائقية؛ محرك InnoDB يدعم المعاملات (Transactions) والمفاتيح "
        "الأجنبية ويُنشئ فهارس للمفاتيح الأجنبية تلقائياً.",
        "en": "MySQL is relational; InnoDB supports transactions and foreign keys and indexes "
        "foreign keys automatically.",
        "points": ["innodb", "transaction", "foreign key", "index", "commit", "rollback"],
        "questions": [
            (
                "ar",
                "challenge",
                3,
                "متى تحتاج معاملة (Transaction) في مشروعك؟ أعطِ مثالاً لعملية لو "
                "نُفّذ نصفها فقط لأفسدت البيانات.",
                ["transaction", "commit", "rollback", "atomic"],
            ),
        ],
    },
    "tech:react": {
        "title": "React",
        "ar": "React تبني الواجهة من مكوّنات، وكل مكوّن يعيد الرسم عند تغيّر حالته (state) أو "
        "خصائصه (props). البيانات تنتقل من الأب إلى الابن.",
        "en": "React builds UIs from components that re-render when state or props change; data "
        "flows from parent to child.",
        "points": ["component", "state", "props", "hook", "useeffect", "render"],
        "questions": [
            (
                "ar",
                "technical",
                2,
                "ما الفرق بين state و props في مكوّنات مشروعك؟",
                ["state", "props", "parent", "render"],
            ),
        ],
    },
}

# Detected names -> topic keys.
VULNERABILITY_TOPICS = {
    "SQL Injection": "vuln:sql_injection",
    "Cross-Site Scripting (XSS)": "vuln:xss",
    "Command Injection": "vuln:command_injection",
    "Code Injection": "vuln:command_injection",
    "Path Traversal": "vuln:path_traversal",
    "Hardcoded Secret": "vuln:hardcoded_secret",
    "Insecure Deserialization": "vuln:insecure_deserialization",
    "Weak Hash Algorithm": "vuln:weak_hash",
}
DATABASE_TOPICS = {
    "repeating_group": "db:normalization",
    "multivalued_column": "db:normalization",
    "partial_dependency": "db:normalization",
    "transitive_dependency": "db:normalization",
    "missing_primary_key": "db:keys",
    "missing_foreign_key": "db:keys",
    "broken_reference": "db:keys",
    "missing_index": "db:indexes",
}
