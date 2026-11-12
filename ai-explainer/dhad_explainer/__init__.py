"""شارح أخطاء ضاد الذكي.

المترجم الحتمي يكتشف الخطأ ويحدد كوده وموقعه؛ هذه الحزمة تشرحه فقط:
شرح عربي متدرج (أربعة مستويات) مقيَّد بصفحات التوثيق الرسمية في docs/errors،
يمر بحارس جودة قبل العرض، ويرجع إلى شرح حتمي من التوثيق عند أي فشل.
"""

from .explainer import Explanation, explain, explain_file
from .guard import GuardResult, check
from .levels import LEVELS

__all__ = ["Explanation", "explain", "explain_file", "GuardResult", "check", "LEVELS"]
