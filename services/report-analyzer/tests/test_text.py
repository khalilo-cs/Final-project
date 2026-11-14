from app.analyzers.fingerprint import winnow
from app.text.normalize import normalize, tokenize


def test_arabic_normalization():
    assert normalize("الأَهْدافُ") == normalize("الاهداف") == "الاهداف"
    assert normalize("مـقـدمـة") == "مقدمه"  # tatweel + taa marbuta
    assert normalize("إدارة المكتبة") == normalize("ادارة المكتبه")
    assert normalize("على مستوى") == "علي مستوي"
    assert normalize("٣ جداول") == "3 جداول"
    assert normalize("ﻻ ﻟﻠﻨﻈﺎم") == "لا للنظام"  # PDF presentation forms
    assert normalize("MySQL") == "mysql"


def test_tokens_keep_original_offsets():
    text = "نظامُ إدارةِ المكتبة 2024 Library"
    tokens = tokenize(text)
    assert [t.text for t in tokens] == ["نظام", "اداره", "المكتبه", "library"]
    assert text[tokens[1].start : tokens[1].end] == "إدارةِ"


def test_voweled_words_stay_whole():
    assert [t.text for t in tokenize("الأَهْدافُ الرَّئِيسِيَّة")] == ["الاهداف", "الرييسيه"]
    assert [t.text for t in tokenize("الأهداف الرئيسية")] == ["الاهداف", "الرييسيه"]


def test_winnowing_guarantee():
    words = [f"w{i}" for i in range(100)]
    base = tokenize(" ".join(words))
    # Any shared run of >= w + k - 1 = 8 words must share a fingerprint.
    copied = tokenize("x y z " + " ".join(words[40:48]) + " q r s")
    assert {f.hash for f in winnow(base)} & {f.hash for f in winnow(copied)}
    # Density: about 2 / (w + 1) of all k-grams are kept.
    assert 20 <= len(winnow(base)) <= 50
    assert winnow(tokenize("too short")) == []
