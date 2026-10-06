"""
import_open_sources.py
سكربت استيراد بيانات حقيقية من مصادر مفتوحة الترخيص إلى corpus.json و sources.json

⚠️ يحتاج اتصال إنترنت فعلي عند التشغيل — شغّله على جهازك (لا داخل بيئة معزولة بدون شبكة).

المصادر المستخدمة (تم التحقق من بنية استجابتها فعلياً قبل كتابة هذا الكود):
1. القرآن الكريم: api.alquran.cloud (نص Tanzil الرسمي، ترخيص CC BY، بدون مفتاح API)
   التوثيق: https://alquran.cloud/api
2. الحديث: fawazahmed0/hadith-api عبر jsDelivr CDN (الكتب التسعة، بدون مفتاح، بدون حد للطلبات)
   التوثيق: https://github.com/fawazahmed0/hadith-api

الاستخدام:
    python3 import_open_sources.py --quran-surahs 112 113 114 1
    python3 import_open_sources.py --hadith-editions ara-bukhari ara-muslim --hadith-limit 100
    python3 import_open_sources.py --quran-surahs 1 112 113 114 --hadith-editions ara-bukhari --hadith-limit 50
"""

import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CORPUS_PATH = DATA_DIR / "corpus.json"
SOURCES_PATH = DATA_DIR / "sources.json"

QURAN_API = "https://api.alquran.cloud/v1"
HADITH_API = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"

# أسماء عربية لطباعة الكتب (لأغراض topic/source_ref فقط)
HADITH_BOOK_NAMES_AR = {
    "bukhari": "صحيح البخاري",
    "muslim": "صحيح مسلم",
    "tirmidhi": "سنن الترمذي",
    "abudawud": "سنن أبي داود",
    "nasai": "سنن النسائي",
    "ibnmajah": "سنن ابن ماجه",
    "malik": "موطأ مالك",
}


def fetch_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "islamic-verify-tool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# القرآن الكريم — api.alquran.cloud
# ---------------------------------------------------------------------------
def import_quran(surah_numbers: list[int], source_id: str = "quran_main") -> list[dict]:
    entries = []
    for surah_no in surah_numbers:
        url = f"{QURAN_API}/surah/{surah_no}/quran-uthmani"
        print(f"  تحميل سورة رقم {surah_no} من {url}")
        try:
            payload = fetch_json(url)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  ⚠️ فشل تحميل سورة {surah_no}: {e}")
            continue

        data = payload.get("data", {})
        surah_name = data.get("name", f"سورة {surah_no}")
        for ayah in data.get("ayahs", []):
            entries.append({
                "id": f"q_{surah_no}_{ayah['numberInSurah']}",
                "type": "quran",
                "text": ayah["text"],
                "source_ref": f"{surah_name}، آية {ayah['numberInSurah']}",
                "topic": data.get("englishNameTranslation", surah_name),
                "evidence_strength": "قرآن كريم - أعلى درجات الثبوت",
                "confidence_score": 1.0,
                "source_id": source_id,
            })
    return entries


# ---------------------------------------------------------------------------
# الحديث — fawazahmed0/hadith-api (نسخة عربية لكل كتاب: ara-<book>)
# ---------------------------------------------------------------------------
def classify_grade(grades: list[dict], book: str) -> tuple[str, float]:
    """
    يحوّل حقل grades (إن وُجد) إلى وصف عربي + درجة ثقة تقريبية.
    ملاحظة: هذا تبسيط عملي للـ MVP — للاستخدام الفعلي راجع درجة كل حديث
    من مصدر تخصصي في التحقق من الأسانيد (مثل الدرر السنية) قبل النشر.
    """
    if grades:
        grade_text = " ".join(g.get("grade", "") for g in grades).lower()
        if "da" in grade_text and "if" in grade_text:  # daif/da'if
            return "حديث ضعيف بحسب التخريج المتاح - يحتاج مراجعة قبل الاستشهاد به", 0.3
        if "mawdu" in grade_text or "fabricated" in grade_text:
            return "حديث موضوع/غير ثابت - لا يصح الاستشهاد به", 0.05
        if "hasan" in grade_text:
            return "حديث حسن بحسب التخريج المتاح", 0.75
        if "sahih" in grade_text:
            return "حديث صحيح بحسب التخريج المتاح", 0.9

    # الكتب الستة المعروفة بصرامة الشرط عند الصحيحين تحديداً
    if book in ("bukhari", "muslim"):
        return "حديث صحيح (من الصحيحين) - يُنصح بالتأكد من رقم الحديث ومطابقته للمصدر الأصلي", 0.9
    return "درجة الحديث غير مؤكدة تلقائياً - راجع مصدراً متخصصاً في التخريج قبل الاستشهاد", 0.5


def import_hadith(editions: list[str], limit: int, source_id_prefix: str = "") -> tuple[list[dict], dict]:
    """
    editions: مثل ['ara-bukhari', 'ara-muslim']
    يرجع (entries, source_id_map) حيث source_id_map يربط كل edition بمعرف مصدر لإضافته لـ sources.json
    """
    entries = []
    source_id_map = {}

    for edition in editions:
        book = edition.replace("ara-", "").replace("1", "")  # ara-bukhari -> bukhari
        source_id = source_id_prefix + book
        source_id_map[edition] = source_id

        url = f"{HADITH_API}/editions/{edition}.json"
        print(f"  تحميل {edition} من {url}")
        try:
            payload = fetch_json(url)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  ⚠️ فشل تحميل {edition}: {e}")
            continue

        book_name_ar = HADITH_BOOK_NAMES_AR.get(book, payload.get("metadata", {}).get("name", book))
        hadiths = payload.get("hadiths", [])[:limit]
        print(f"    ({len(hadiths)} حديث من أصل {len(payload.get('hadiths', []))} — محدود بـ --hadith-limit)")

        for h in hadiths:
            evidence_strength, confidence = classify_grade(h.get("grades", []), book)
            num = h.get("hadithnumber", h.get("arabicnumber", "?"))
            entries.append({
                "id": f"h_{book}_{num}",
                "type": "hadith",
                "text": h.get("text", "").strip(),
                "source_ref": f"{book_name_ar}، حديث رقم {num}",
                "topic": book_name_ar,
                "evidence_strength": evidence_strength,
                "confidence_score": confidence,
                "source_id": source_id,
            })

    return entries, source_id_map


# ---------------------------------------------------------------------------
# الدمج مع corpus.json و sources.json الحاليين
# ---------------------------------------------------------------------------
def merge_into_corpus(new_entries: list[dict]) -> int:
    existing = load_json(CORPUS_PATH) if CORPUS_PATH.exists() else []
    existing_ids = {d["id"] for d in existing}
    added = 0
    for entry in new_entries:
        if entry["id"] in existing_ids:
            continue  # لا نكرر نفس المعرف عند إعادة التشغيل
        existing.append(entry)
        existing_ids.add(entry["id"])
        added += 1
    save_json(CORPUS_PATH, existing)
    return added


def merge_into_sources(source_id_map: dict, arabic_names: dict) -> int:
    existing = load_json(SOURCES_PATH) if SOURCES_PATH.exists() else []
    existing_ids = {s["id"] for s in existing}
    added = 0
    for edition, source_id in source_id_map.items():
        if source_id in existing_ids:
            continue
        existing.append({
            "id": source_id,
            "name": arabic_names.get(source_id, source_id),
            "enabled": True,
        })
        existing_ids.add(source_id)
        added += 1
    save_json(SOURCES_PATH, existing)
    return added


def main():
    parser = argparse.ArgumentParser(description="استيراد مصادر حقيقية إلى قاعدة بيانات المشروع")
    parser.add_argument("--quran-surahs", nargs="*", type=int, default=[],
                         help="أرقام السور المراد استيرادها (مثال: 1 112 113 114)")
    parser.add_argument("--hadith-editions", nargs="*", default=[],
                         help="نسخ عربية من fawazahmed0/hadith-api (مثال: ara-bukhari ara-muslim)")
    parser.add_argument("--hadith-limit", type=int, default=100,
                         help="أقصى عدد أحاديث لكل كتاب (افتراضي 100 لتفادي تضخيم القاعدة)")
    args = parser.parse_args()

    if not args.quran_surahs and not args.hadith_editions:
        print("لم تحدد أي مصدر. استخدم --quran-surahs و/أو --hadith-editions. جرّب --help لمزيد.")
        return

    all_new_entries = []

    if args.quran_surahs:
        print(f"\n📖 استيراد {len(args.quran_surahs)} سورة من القرآن الكريم...")
        all_new_entries += import_quran(args.quran_surahs)

    if args.hadith_editions:
        print(f"\n📚 استيراد الحديث من: {', '.join(args.hadith_editions)}...")
        hadith_entries, source_id_map = import_hadith(args.hadith_editions, args.hadith_limit)
        all_new_entries += hadith_entries
        arabic_names = {sid: HADITH_BOOK_NAMES_AR.get(sid, sid) for sid in source_id_map.values()}
        n_sources = merge_into_sources(source_id_map, arabic_names)
        print(f"  ✅ أُضيف {n_sources} مصدر جديد إلى sources.json")

    added = merge_into_corpus(all_new_entries)
    print(f"\n✅ تمت إضافة {added} نص جديد إلى corpus.json (من أصل {len(all_new_entries)} تم جلبه، "
          f"البقية موجودة مسبقاً).")
    print("شغّل retrieval.py أو أعد تشغيل app.py ليأخذ الفهرس التحديثات الجديدة.")


if __name__ == "__main__":
    main()
