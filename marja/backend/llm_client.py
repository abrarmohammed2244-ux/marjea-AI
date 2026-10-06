"""
طبقة الصياغة الاختيارية باستخدام Google Gemini API.

تحافظ على الواجهة التي يستدعيها app.py:
    generate_grounded_answer(query, sources)

الإعدادات المدعومة في البيئة أو ملف .env:
    GEMINI_API_KEY=...
    GEMINI_MODEL=gemini-2.5-flash
    GEMINI_TIMEOUT=45
"""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # يعمل أيضاً بدون dependency عند استخدام متغيرات البيئة مباشرة
    load_dotenv = None


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
GEMINI_TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", "45"))

# يسمح للمستخدم بكتابة models/foo أو foo في ملف البيئة.
if GEMINI_MODEL.startswith("models/"):
    GEMINI_MODEL = GEMINI_MODEL.removeprefix("models/")

SYSTEM_INSTRUCTION = """أنت مساعد بحث للمعرّفين بالإسلام والباحثين الشرعيين.
قواعد صارمة:
1. أجب فقط اعتماداً على المقتطفات المرفقة، ولا تستخدم معرفتك العامة.
2. اذكر مصدر كل معلومة كما هو مكتوب في المقتطف.
3. إذا لم تكفِ المقتطفات، قل بوضوح إن المصادر المتاحة لا تكفي وأنه ينبغي مراجعة مختص شرعي.
4. لا تصدر فتوى أو حكماً قاطعاً في مسائل الخلاف.
5. لا تحكم من عندك على صحة حديث أو درجته؛ انسب الحكم إلى المصدر نفسه.
6. كن موجزاً ودقيقاً وبالعربية.
"""


def _build_context(sources: list[dict]) -> str:
    if not sources:
        return "لا توجد مقتطفات مسترجعة."

    blocks = []
    for i, source in enumerate(sources, 1):
        blocks.append(
            f"[مقتطف {i}]\n"
            f"النص: {source.get('text', '')}\n"
            f"المصدر: {source.get('source_ref', 'غير محدد')}\n"
            f"درجة الدليل: {source.get('evidence_strength', 'غير محدد')}\n"
        )
    return "\n".join(blocks)


# رسائل مناسبة للمستخدم فقط — بلا أي مصطلحات تقنية (رمز HTTP، نص الاستثناء) وبلا
# ذكر اسم أي مزوّد أو موديل بعينه؛ نقول "مولّد الذكاء الاصطناعي" دائماً. التفاصيل
# التقنية الحقيقية (رمز الخطأ، نص الاستثناء) تُسجَّل فقط في سجلات السيرفر (LOGGER)
# ولا تُرسل أبداً إلى الواجهة — حتى لا تتسرب لأي زائر يفتح الرابط العام.
_USER_MESSAGES = {
    "not_configured": "صياغة الإجابات بمولّد الذكاء الاصطناعي غير مُفعّلة حالياً.",
    "busy": "مولّد الذكاء الاصطناعي مزدحم حالياً، يرجى المحاولة مرة أخرى بعد قليل.",
    "unavailable": "تعذّر الوصول إلى مولّد الذكاء الاصطناعي حالياً، يرجى المحاولة مرة أخرى بعد قليل.",
}


def _unavailable(reason: str) -> dict:
    """
    استجابة موحّدة عند عدم توفر التوليد الذكي لأي سبب — لا تُعيد نص المصادر
    بالطريقة التقليدية (مكرر مع قائمة النتائج المعروضة أصلاً أسفل الصفحة)،
    بل رسالة قصيرة فقط تُرشد المستخدم للرجوع للنتائج المسترجعة مباشرة.
    """
    return {
        "answer": None,
        "mode": "unavailable",
        "message": _USER_MESSAGES.get(reason, _USER_MESSAGES["unavailable"]),
        "sources_used": [],
    }


def _extract_text(data: dict) -> str:
    parts = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part, dict) and part.get("text"):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def generate_grounded_answer(query: str, sources: list[dict]) -> dict:
    """
    يصوغ إجابة مقيدة حصراً بالمصادر المسترجعة (retrieval-augmented) عبر موديل
    توليدي خارجي. النموذج يعتمد فقط على ما تم استرجاعه محلياً من قاعدة المصادر —
    لا يبحث هو نفسه ولا يضيف من معرفته العامة (مفروض عليه بـ SYSTEM_INSTRUCTION).
    عند أي عطل أو ازدحام، تُعاد رسالة مناسبة للمستخدم فقط دون تفاصيل تقنية ودون
    عرض نص المصادر بالطريقة التقليدية (هي معروضة أصلاً أسفل الصفحة في كل الأحوال).
    """
    if not GEMINI_API_KEY:
        return _unavailable("not_configured")

    prompt = (
        f"تعليمات النظام:\n{SYSTEM_INSTRUCTION}\n\n"
        f"السؤال: {query}\n\n"
        f"المقتطفات المسترجعة من قاعدة المصادر:\n{_build_context(sources)}\n\n"
        "أجب اعتماداً حصراً على المقتطفات أعلاه، مع ذكر مصدر كل نقطة."
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 5000},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
        answer = _extract_text(data)
        if not answer:
            LOGGER.warning("Gemini returned no text")
            return _unavailable("unavailable")
        return {
            "answer": answer,
            "mode": "gemini_generated",
            "sources_used": [s.get("source_ref", "غير محدد") for s in sources],
        }
    except urllib.error.HTTPError as error:
        # التفاصيل التقنية (الرمز ونص الخطأ) تُسجَّل في سجل السيرفر فقط لتشخيصها
        # لاحقاً، ولا تُرسل إطلاقاً للواجهة. 429 (تجاوز الحصة) و503 (ازدحام
        # الخدمة) كلاهما يُعرض للمستخدم كـ"مزدحم حالياً" — فرق لا يهمّه، يهمّه
        # أن يحاول لاحقاً. أي رمز آخر يُعرض كـ"غير متاح حالياً".
        try:
            details = error.read().decode("utf-8", "replace")[:500]
        except Exception:
            details = str(error)
        LOGGER.warning("Gemini HTTP error %s: %s", error.code, details)
        reason = "busy" if error.code in (429, 503) else "unavailable"
        return _unavailable(reason)
    except (urllib.error.URLError, TimeoutError) as error:
        LOGGER.warning("Gemini connection error: %s", error)
        return _unavailable("unavailable")
    except (ValueError, json.JSONDecodeError) as error:
        LOGGER.warning("Invalid Gemini response: %s", error)
        return _unavailable("unavailable")
    except Exception as error:
        LOGGER.exception("Unexpected Gemini error")
        return _unavailable("unavailable")


if __name__ == "__main__":
    result = generate_grounded_answer(
        "ما معنى النية؟",
        [{
            "text": "إنما الأعمال بالنيات",
            "source_ref": "صحيح البخاري، حديث 1",
            "evidence_strength": "حديث صحيح",
        }],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
