"""
import_local_hadith_json.py
استيراد من قاعدة بيانات "hadith-json" (AhmedBaset/hadith-json) — نسخة محلية، بدون إنترنت.

المصدر: 50,884 حديثاً من 17 كتاباً، بالنص العربي الكامل (بالسند)، مأخوذة أصلاً من Sunnah.com.
البنية الفعلية لكل ملف db/by_book/<فئة>/<كتاب>.json (تم فحصها مباشرة):
{
  "id": ..., "metadata": {"arabic": {"title": ..., "author": ...}, ...},
  "chapters": [{"id":.., "arabic":.., "english":..}, ...],
  "hadiths": [{"id":.., "idInBook":.., "chapterId":.., "arabic":.., "english":{...}}, ...]
}

⚠️ ملاحظتان مهمتان قبل الاستخدام في التسليم النهائي:
1. لا يحتوي هذا المصدر على حقل "درجة الحديث" (صحيح/حسن/ضعيف) لأي حديث. القيم الافتراضية
   أدناه تصنيف عام حسب سُمعة الكتاب فقط، وليست تخريجاً فعلياً لكل حديث على حدة.
2. لم يُعثر على ملف LICENSE صريح في المستودع، والبيانات مصرَّح في الـ README أنها
   "scraped from Sunnah.com". راجع شروط الاستخدام الخاصة بـ Sunnah.com (sunnah.com/about)
   بخصوص إعادة النشر بالجملة قبل اعتماد هذا المصدر رسمياً في مشروع يُسلَّم لمسابقة عامة.

الاستخدام:
    python3 import_local_hadith_json.py --source-dir /path/to/hadith-json-main --limit 300
    python3 import_local_hadith_json.py --source-dir /path/to/hadith-json-main --books bukhari muslim --limit 0
    (limit 0 = استيراد كل الأحاديث بدون حد)
"""

import json
import argparse
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CORPUS_PATH = DATA_DIR / "corpus.json"
SOURCES_PATH = DATA_DIR / "sources.json"

# تصنيف افتراضي عام حسب سُمعة الكتاب (لا يغني عن تخريج فعلي لكل حديث)
BOOK_DEFAULT_STRENGTH = {
    "bukhari": ("حديث من صحيح البخاري - يُعد من أصح كتب الحديث، لكن هذا المصدر لا يقدم تخريجاً "
                "لكل حديث على حدة؛ راجع مصدراً متخصصاً بالتخريج قبل الاستشهاد الحساس", 0.85),
    "muslim": ("حديث من صحيح مسلم - يُعد من أصح كتب الحديث، لكن هذا المصدر لا يقدم تخريجاً "
               "لكل حديث على حدة؛ راجع مصدراً متخصصاً بالتخريج قبل الاستشهاد الحساس", 0.85),
    "abudawud": ("حديث من سنن أبي داود - تتفاوت درجة أحاديثه بين الصحة والضعف؛ "
                 "لا تخريج فعلياً بهذا المصدر، راجع تخريجاً متخصصاً", 0.5),
    "tirmidhi": ("حديث من جامع الترمذي - تتفاوت درجة أحاديثه؛ لا تخريج فعلي بهذا المصدر، "
                 "راجع تخريجاً متخصصاً", 0.5),
    "nasai": ("حديث من سنن النسائي - تتفاوت درجة أحاديثه؛ لا تخريج فعلي بهذا المصدر، "
              "راجع تخريجاً متخصصاً", 0.5),
    "ibnmajah": ("حديث من سنن ابن ماجه - تتفاوت درجة أحاديثه (فيه أحاديث ضعيفة نسبياً أكثر من "
                 "غيره)؛ لا تخريج فعلي بهذا المصدر، راجع تخريجاً متخصصاً قبل الاستشهاد", 0.4),
    "malik": ("حديث من موطأ مالك - يُعد من أقدم وأوثق كتب الحديث عموماً؛ لا تخريج فعلي بهذا "
              "المصدر لكل حديث", 0.7),
    "ahmed": ("حديث من مسند الإمام أحمد - تتفاوت درجة أحاديثه بشدة؛ لا تخريج فعلي بهذا المصدر، "
              "راجع تخريجاً متخصصاً قبل أي استشهاد", 0.4),
    "darimi": ("حديث من سنن الدارمي - تتفاوت درجة أحاديثه؛ لا تخريج فعلي بهذا المصدر، "
               "راجع تخريجاً متخصصاً", 0.45),
}
# افتراضي لأي كتاب غير مذكور أعلاه (المختارات مثل رياض الصالحين، الأربعينات، إلخ)
GENERIC_DEFAULT_STRENGTH = ("حديث من مجموعة مختارة موثوقة عموماً؛ هذا المصدر لا يقدم تخريجاً "
                             "فعلياً لكل حديث، راجع مصدراً متخصصاً قبل الاستشهاد الحساس", 0.55)


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def import_book_file(book_file: Path, book_slug: str, limit: int) -> tuple[list[dict], str]:
    data = load_json(book_file)
    book_title_ar = data["metadata"]["arabic"]["title"]
    chapters = {c["id"]: c["arabic"] for c in data.get("chapters", [])}

    hadiths = data["hadiths"]
    if limit > 0:
        hadiths = hadiths[:limit]

    strength_text, confidence = BOOK_DEFAULT_STRENGTH.get(book_slug, GENERIC_DEFAULT_STRENGTH)

    entries = []
    for h in hadiths:
        chapter_name = chapters.get(h.get("chapterId"), book_title_ar)
        entries.append({
            "id": f"h_{book_slug}_{h['idInBook']}",
            "type": "hadith",
            "text": h["arabic"].strip(),
            "source_ref": f"{book_title_ar}، حديث رقم {h['idInBook']}",
            "topic": chapter_name,
            "evidence_strength": strength_text,
            "confidence_score": confidence,
            "source_id": book_slug,
        })
    return entries, book_title_ar


def merge_into_corpus(new_entries: list[dict]) -> int:
    existing = load_json(CORPUS_PATH) if CORPUS_PATH.exists() else []
    existing_ids = {d["id"] for d in existing}
    added = 0
    for entry in new_entries:
        if entry["id"] in existing_ids:
            continue
        existing.append(entry)
        existing_ids.add(entry["id"])
        added += 1
    save_json(CORPUS_PATH, existing)
    return added


def merge_into_sources(book_slug_to_name: dict) -> int:
    existing = load_json(SOURCES_PATH) if SOURCES_PATH.exists() else []
    existing_ids = {s["id"] for s in existing}
    added = 0
    for slug, name in book_slug_to_name.items():
        if slug in existing_ids:
            continue
        existing.append({"id": slug, "name": name, "enabled": True})
        existing_ids.add(slug)
        added += 1
    save_json(SOURCES_PATH, existing)
    return added


def main():
    parser = argparse.ArgumentParser(description="استيراد من قاعدة hadith-json المحلية")
    parser.add_argument("--source-dir", required=True,
                         help="مسار مجلد hadith-json-main (يحتوي على db/by_book)")
    parser.add_argument("--books", nargs="*", default=None,
                         help="أسماء الكتب المراد استيرادها (بدون .json). افتراضياً: كل الكتب المتاحة")
    parser.add_argument("--limit", type=int, default=300,
                         help="أقصى عدد أحاديث لكل كتاب (0 = بدون حد، استيراد الكل)")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    by_book_dir = source_dir / "db" / "by_book"
    if not by_book_dir.exists():
        print(f"❌ لم يُعثر على {by_book_dir} — تأكد من مسار --source-dir")
        return

    all_book_files = sorted(by_book_dir.glob("*/*.json"))
    if args.books:
        wanted = set(args.books)
        all_book_files = [f for f in all_book_files if f.stem in wanted]

    if not all_book_files:
        print("لم يتم العثور على أي ملف كتاب مطابق.")
        return

    print(f"سيتم استيراد {len(all_book_files)} كتاباً (حد {args.limit or 'بدون حد'} حديث لكل كتاب):\n")

    all_entries = []
    book_slug_to_name = {}
    for book_file in all_book_files:
        book_slug = book_file.stem
        entries, book_title_ar = import_book_file(book_file, book_slug, args.limit)
        print(f"  📚 {book_title_ar} ({book_slug}): {len(entries)} حديث")
        all_entries += entries
        book_slug_to_name[book_slug] = book_title_ar

    n_sources = merge_into_sources(book_slug_to_name)
    added = merge_into_corpus(all_entries)

    print(f"\n✅ أُضيف {n_sources} مصدر جديد إلى sources.json")
    print(f"✅ أُضيف {added} حديث جديد إلى corpus.json (من أصل {len(all_entries)} تم معالجته)")
    print("\n⚠️ تذكير: هذا المصدر بلا تخريج فعلي لكل حديث، وبلا ملف ترخيص صريح بالمستودع "
          "(البيانات مصرَّح أنها مأخوذة من Sunnah.com). راجع الملاحظات أعلى هذا الملف قبل التسليم النهائي.")


if __name__ == "__main__":
    main()
