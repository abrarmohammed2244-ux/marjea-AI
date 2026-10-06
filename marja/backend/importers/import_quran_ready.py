"""
import_quran_ready.py
استيراد القرآن الكريم كاملاً من ملف quran_ready.json (6,236 آية، صيغة جاهزة ونظيفة).

بنية كل عنصر بالملف المصدر:
{"surah_number": 1, "surah_name": "الفاتحة", "ayah_number": 1, "text": "...", "reference": "سورة الفاتحة - آية 1"}

الاستخدام:
    python3 import_quran_ready.py --source-file /path/to/quran_ready.json
"""

import json
import argparse
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CORPUS_PATH = DATA_DIR / "corpus.json"
SOURCES_PATH = DATA_DIR / "sources.json"


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def convert(quran_data: list[dict], source_id: str = "quran_main") -> list[dict]:
    entries = []
    for v in quran_data:
        entries.append({
            "id": f"q_{v['surah_number']}_{v['ayah_number']}",
            "type": "quran",
            "text": v["text"],
            "source_ref": v.get("reference", f"سورة {v['surah_name']}، آية {v['ayah_number']}"),
            "topic": v["surah_name"],
            "evidence_strength": "قرآن كريم - أعلى درجات الثبوت",
            "confidence_score": 1.0,
            "source_id": source_id,
        })
    return entries


def main():
    parser = argparse.ArgumentParser(description="استيراد القرآن الكامل من quran_ready.json")
    parser.add_argument("--source-file", required=True, help="مسار ملف quran_ready.json")
    args = parser.parse_args()

    quran_data = load_json(Path(args.source_file))
    print(f"تم تحميل {len(quran_data)} آية من الملف المصدر.")

    new_entries = convert(quran_data)

    # نستبدل كل ما هو من نوع quran بالكامل (بدل الدمج) لضمان عدم بقاء بيانات قديمة/جزئية
    existing = load_json(CORPUS_PATH) if CORPUS_PATH.exists() else []
    existing_non_quran = [d for d in existing if d.get("type") != "quran"]
    removed = len(existing) - len(existing_non_quran)

    final_corpus = existing_non_quran + new_entries
    save_json(CORPUS_PATH, final_corpus)

    print(f"🗑️  أُزيل {removed} نصاً قرآنياً قديماً (نموذجي/جزئي).")
    print(f"✅ أُضيف {len(new_entries)} آية كاملة (القرآن كاملاً).")
    print(f"📊 حجم القاعدة الآن: {len(final_corpus)} نصاً.")


if __name__ == "__main__":
    main()
