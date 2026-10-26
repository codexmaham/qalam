"""Letter and word practice, one sheet per language.

The sheet is dotted handwriting on the paper that language is taught on:
four-line English, Urdu copy, tianzige, genkō yōshi, or wongoji.
"""

from __future__ import annotations

PRACTICE: dict[str, dict[str, str]] = {
    "en": {
        "template": "four-line",
        "letters": "A a B b C c D d E e F f G g\nH h I i J j K k L l M m N n\nO o P p Q q R r S s T t U u\nV v W w X x Y y Z z",
        "words": "cat\nsat\nmat\nhat\npen\nbook\nschool\nwrite",
    },
    "ur": {
        "template": "urdu-copy",
        "letters": "ا ب پ ت ٹ ث ج چ ح خ\nد ڈ ذ ر ڑ ز ژ س ش\nص ض ط ظ ع غ ف ق\nک گ ل م ن و ہ ء ی",
        "words": "قلم\nکتاب\nسبق\nاستاد\nبچہ",
    },
    "hi": {
        "template": "single-ruled",
        "letters": "अ आ इ ई उ ऊ ए ऐ ओ औ\nक ख ग घ ङ च छ ज झ ञ\nट ठ ड ढ ण त थ द ध न\nप फ ब भ म य र ल व श ष स ह",
        "words": "कलम\nकिताब\nस्कूल\nपानी\nभारत",
    },
    "ar": {
        "template": "single-ruled",
        "letters": "ا ب ت ث ج ح خ د ذ ر ز س ش\nص ض ط ظ ع غ ف ق ك ل م ن ه و ي",
        "words": "قلم\nكتاب\nمدرسة\nولد\nبنت",
    },
    "zh-hans": {
        "template": "tianzige",
        "letters": "一二三四五六七八九十\n人大小上下中日月水火",
        "words": "学生\n学校\n中国\n你好\n学习",
    },
    "ja": {
        "template": "genko",
        "letters": "あいうえおかきくけこさしすせそ\nたちつてとなにぬねのはひふへほ",
        "words": "学生\n学校\n日本\nこんにちは",
    },
    "ko": {
        "template": "wongoji",
        "letters": "가나다라마바사아자차카타파하\n갸냐댜랴먀뱌샤야쟈챠캬탸퍄햐",
        "words": "학교\n학생\n한국\n안녕",
    },
}


def practice_for(language_id: str, kind: str, sample: str, recommended: list[str]) -> dict:
    kind = "words" if kind == "words" else "letters"
    row = PRACTICE.get(language_id)
    if row:
        return {"text": row[kind], "template": row["template"], "trace": True, "kind": kind}
    template = recommended[0] if recommended else "single-ruled"
    if kind == "words":
        words = [piece for piece in sample.replace("\n", " ").split(" ") if piece][:8]
        text = "\n".join(words) if words else sample
    else:
        text = sample
    return {"text": text, "template": template, "trace": True, "kind": kind}
