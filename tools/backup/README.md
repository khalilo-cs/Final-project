# النسخ الاحتياطي والاسترجاع

خدمة `backup` في `docker-compose.yml` تأخذ نسخة كل يوم (الساعة `BACKUP_HOUR` بتوقيت UTC):

- قاعدة البيانات كاملة (`pg_dump` بصيغة custom مضغوطة).
- ملفات المشاريع المرفوعة. تبقى مشفرة بـ AES-256 إن كان `STORAGE_ENCRYPTION_KEY` مضبوطاً.
- ملف `SHA256SUMS` للتحقق من سلامة النسخة قبل الاسترجاع.

تُحذف النسخ الأقدم من `BACKUP_KEEP_DAYS` يوماً، ولا تُحذف أحدث نسخة أبداً. اجعل `BACKUP_PATH`
قرصاً خارجياً حتى لا يضيع النظام والنسخ معاً إذا تعطل قرص الخادم.

## نسخة يدوية الآن

```sh
docker compose run --rm backup /tools/backup.sh
```

## الاسترجاع (أقل من ساعة)

```sh
docker compose stop project-service auth-service viva-engine report-analyzer fraud-detector
docker compose run --rm backup /tools/restore.sh /backups/mihakk-YYYYMMDD-HHMMSS
docker compose up -d
```

يتحقق `restore.sh` من `SHA256SUMS` أولاً ويرفض النسخة التالفة. ملفات الطلاب المشفرة تحتاج نفس
`STORAGE_ENCRYPTION_KEY` الذي شُفّرت به؛ احفظه خارج الخادم.

جُرّب النسخ والاسترجاع والتدوير على PostgreSQL 16 حقيقي: عادت الدرجات والملفات كما كانت بعد تعديلها.
