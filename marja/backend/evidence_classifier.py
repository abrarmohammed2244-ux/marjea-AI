"""
وحدة تقييم قوة الدليل (Evidence Strength Classifier)
تصنّف كل نتيجة بحث حسب نوعها لتعطي الباحث فكرة سريعة عن مدى الثقة الواجب إعطاؤها للنص.

المستويات (من الأعلى ثقة للأدنى):
1. نص قرآني  -> ثبوت قطعي
2. حديث صحيح -> ثبوت عالٍ جداً
3. حديث حسن  -> ثبوت جيد لكن دون الصحيح
4. رأي فقهي مجمع/راجح -> رأي معتبر لدى الجمهور
5. خلاف فقهي معتبر -> يحتاج بيان الخلاف لا جواب واحد قاطع
6. يتطلب إحالة لمختص -> النظام يمتنع عن الحسم ويحيل
"""

STRENGTH_LEVELS = {
    "quran": {
        "label": "نص قرآني",
        "tier": 1,
        "description": "أعلى درجات الثبوت، لا يقبل الشك في نسبته",
        "color": "green",
    },
    "hadith_sahih": {
        "label": "حديث صحيح",
        "tier": 2,
        "description": "ثبوت عالٍ جداً وفق علم الحديث",
        "color": "green",
    },
    "hadith_hasan": {
        "label": "حديث حسن",
        "tier": 3,
        "description": "ثبوت جيد، لكن دون درجة الصحيح",
        "color": "lightgreen",
    },
    "requires_referral": {
        "label": "يتطلب إحالة لمختص",
        "tier": 6,
        "description": "حالة فردية معقدة لا يصح فيها جواب عام آلي",
        "color": "red",
    },
}


def classify_by_metadata(doc: dict) -> dict:
    """
    تصنيف مبدئي بناءً على نوع المصدر ومحتوى وصف قوة الدليل في القاعدة.
    هذا تصنيف بقواعد صريحة (deterministic) - أكثر أماناً من الاعتماد الكامل على LLM
    لأنه لا يتغير أو "يهلوس" بين تشغيل وآخر.

    ملاحظة: النطاق الحالي للمشروع (قرآن + حديث فقط، بدون فتاوى) — منطق تصنيف الفتاوى
    أُزيل من هنا. لو أُضيف مصدر فتاوى لاحقاً، أضف فرعاً مخصصاً بنفس الأسلوب.
    """
    doc_type = doc.get("type", "")
    strength_text = doc.get("evidence_strength", "")

    if doc_type == "quran":
        level_key = "quran"
    elif doc_type == "hadith":
        if "حسن" in strength_text:
            level_key = "hadith_hasan"
        elif "ضعيف" in strength_text or "موضوع" in strength_text:
            level_key = "requires_referral"
        else:
            level_key = "hadith_sahih"
    else:
        level_key = "requires_referral"

    level = STRENGTH_LEVELS[level_key]
    return {
        "level_key": level_key,
        "label": level["label"],
        "tier": level["tier"],
        "description": level["description"],
        "color": level["color"],
        "raw_confidence_score": doc.get("confidence_score", None),
    }


if __name__ == "__main__":
    import json
    with open("data/corpus.json", encoding="utf-8") as f:
        corpus = json.load(f)
    for doc in corpus:
        classification = classify_by_metadata(doc)
        print(f"[{classification['label']:25}] {doc['text'][:40]}...")
