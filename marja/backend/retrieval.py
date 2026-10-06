"""
محرك البحث والاسترجاع (Retrieval Engine)
يستخدم TF-IDF + تشابه جيب التمام (Cosine Similarity) فوق طبقة دلالية عربية خفيفة:
اشتقاق (stemming) يزيل البادئات/اللواحق الشائعة ليوحّد صيغ الكلمة الواحدة (صيام/الصيام/صائم)،
+ قاموس مرادفات مختصر لأهم المصطلحات الشرعية المتكررة التي لا يحلّها الاشتقاق وحده.

ملاحظة أمانة فنية: هذا تحسين دلالي خفيف (lightweight) يعمل بالكامل محلياً بدون إنترنت
أو نماذج خارجية — وليس بديلاً كاملاً عن تضمين دلالي عصبي حقيقي (مثل AraBERT embeddings).
الواجهة (دالة search) مصممة بحيث يسهل استبدال طبقة الاشتقاق لاحقاً بنموذج embeddings
حقيقي دون تغيير بقية الكود.
"""

import json
import re
import math
from collections import Counter
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "corpus.json"
SOURCES_PATH = Path(__file__).parent / "data" / "sources.json"

ARABIC_DIACRITICS = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED]')


def normalize_arabic(text: str) -> str:
    """توحيد أشكال الحروف العربية وإزالة التشكيل لتحسين المطابقة."""
    text = ARABIC_DIACRITICS.sub('', text)
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'ى', 'ي', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ؤ', 'و', text)
    text = re.sub(r'ئ', 'ي', text)
    text = re.sub(r'ـ', '', text)  # تطويل
    text = re.sub(r'[^\w\s]', ' ', text)
    return text.strip()


STOPWORDS = {
    'من', 'الي', 'الى', 'عن', 'علي', 'على', 'في', 'ان', 'انه', 'اللذي', 'الذي',
    'التي', 'هذا', 'هذه', 'ذلك', 'تلك', 'لا', 'لم', 'لن', 'ما', 'او', 'ثم',
    'قد', 'كان', 'كانت', 'يكون', 'له', 'لها', 'لهم', 'به', 'بها', 'هو', 'هي',
    'هم', 'انا', 'انت', 'نحن', 'كل', 'بعض', 'غير', 'بين', 'عند', 'مع', 'اذا',
    'حتي', 'حتى', 'او', 'ولا', 'وان', 'فان', 'الله'
}


def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    normalized = normalize_arabic(text)
    tokens = [t for t in normalized.split() if len(t) > 1]
    if remove_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


# --- طبقة الاشتقاق العربي الخفيف (Light Arabic Stemming) -------------------
# بادئات شائعة (أطول تطابق أولاً) تُزال إن بقي من الكلمة 3 أحرف فأكثر
_PREFIXES = ["وبال", "فبال", "بال", "كال", "وال", "فال", "لل", "ال", "و", "ف", "ب", "ل", "ك"]
# لواحق شائعة (أطول تطابق أولاً) تُزال إن بقي من الكلمة 3 أحرف فأكثر
_SUFFIXES = ["تين", "هما", "هن", "كن", "ون", "ين", "ات", "تم", "تن", "نا", "كم",
             "وا", "ان", "ية", "ه", "ا", "ي", "ن"]


def strip_prefix(word: str) -> str:
    """يزيل بادئة واحدة كحد أقصى (الأطول تطابقاً أولاً)، بشرط بقاء 3 أحرف فأكثر."""
    if len(word) <= 3:
        return word
    for prefix in _PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix):]
    return word


def strip_suffix(word: str) -> str:
    """يزيل لاحقة واحدة كحد أقصى (الأطول تطابقاً أولاً)، بشرط بقاء 3 أحرف فأكثر."""
    if len(word) <= 3:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def light_stem(word: str) -> str:
    """
    اشتقاق خفيف: يزيل بادئة ثم لاحقة (كحد أقصى واحدة من كل نوع)، بشرط ألا يقل
    طول الجذر الناتج عن 3 أحرف — لتفادي تشويه الكلمات القصيرة. ليس اشتقاقاً
    صرفياً دقيقاً (لا يعرف الوزن الصرفي)، لكنه كافٍ عملياً لتوحيد أغلب صيغ
    نفس الكلمة (صيام/الصيام/صائم/صاموا) تحت جذر واحد تقريبي.
    """
    return strip_suffix(strip_prefix(word))


# قاموس مرادفات مختصر لأهم المصطلحات الشرعية المتكررة (بعد normalize_arabic:
# التاء المربوطة ← ه، الألف بأشكالها ← ا). يُطبَّق على الكلمة الخام قبل الاشتقاق
# لتغطية صيغاً لا يحلّها الاشتقاق وحده (جموع تكسير، أفعال غير منتظمة...).
SYNONYMS = {
    # الصيام (الهمزة في "صائم" تتحول إلى ياء بعد normalize_arabic: صايم)
    "صيام": "صوم", "صايم": "صوم", "صايمين": "صوم", "صوموا": "صوم", "يصوم": "صوم",
    # الصلاة (أغلب الصيغ يحلها الاشتقاق عبر إزالة "ال"، هذي لصيغ الفعل)
    "يصلي": "صلاه", "صلوا": "صلاه", "مصلي": "صلاه", "الصلوات": "صلاه",
    # الزكاة والصدقة
    "زكاه": "زكاه", "تزكيه": "زكاه", "صدقه": "صدقه", "يتصدق": "صدقه",
    "صدقات": "صدقه", "متصدق": "صدقه",
    # الحج (جذر قصير حرفين، لا يقصّه حارس الطول بالاشتقاق، فيُعامل كحالة خاصة)
    "الحج": "حج", "حجاج": "حج", "يحج": "حج", "حاج": "حج", "الحجيج": "حج",
    # الجهاد
    "يجاهد": "جهاد", "مجاهد": "جهاد", "مجاهدين": "جهاد",
    # النية
    "نيه": "نيه", "ينوي": "نيه", "نيات": "نيه", "النوايا": "نيه",
    # التوبة (الهمزة في "تائب" تتحول إلى ياء بعد normalize_arabic: تايب)
    "يتوب": "توبه", "تايب": "توبه", "توبوا": "توبه", "التوابين": "توبه",
    # الصبر
    "يصبر": "صبر", "صابر": "صبر", "صابرين": "صبر", "اصبروا": "صبر",
    # الرحمة
    "يرحم": "رحمه", "راحم": "رحمه", "الراحمين": "رحمه", "رحيم": "رحمه",
    # العدل
    "يعدل": "عدل", "عادل": "عدل", "العادلين": "عدل",
    # الكذب والصدق
    "يكذب": "كذب", "كاذب": "كذب", "يصدق": "صدق", "صادق": "صدق", "صادقين": "صدق",
}


def semantic_tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    """
    التجزيء الدلالي المستخدم فعلياً في الفهرسة والبحث:
    تطبيع ← إزالة كلمات وقف ← إزالة البادئة ← تطبيق قاموس المرادفات (على الكلمة
    بعد إزالة البادئة، حتى تنطبق "الصابرين" كما تنطبق "صابرين") ← إزالة اللاحقة.
    الناتج "جذور" وليس كلمات خام، فكل صيغ نفس الكلمة (أو مرادفاتها المعروفة)
    تتجمع تحت نفس الرمز في فهرس TF-IDF.
    """
    tokens = tokenize(text, remove_stopwords=remove_stopwords)
    stems = []
    for t in tokens:
        no_prefix = strip_prefix(t)
        mapped = SYNONYMS.get(no_prefix, SYNONYMS.get(t, no_prefix))
        stems.append(strip_suffix(mapped))
    return stems


def load_sources_config(path: Path = SOURCES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_sources_config(sources: list[dict], path: Path = SOURCES_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)


class RetrievalEngine:
    def __init__(self, corpus_path: Path = DATA_PATH, sources_path: Path = SOURCES_PATH):
        self.corpus_path = corpus_path
        self.sources_path = sources_path
        self.reload()

    def reload(self):
        """يعيد تحميل قاعدة المصادر وإعدادات التفعيل/التعطيل من القرص، ويعيد بناء الفهرس."""
        with open(self.corpus_path, encoding="utf-8") as f:
            full_corpus = json.load(f)
        self.sources_config = load_sources_config(self.sources_path)
        enabled_ids = {s["id"] for s in self.sources_config if s.get("enabled", True)}
        # لو مصدر ما إله source_id، نعتبره مفعّل دائماً (توافق مع بيانات قديمة)
        self.corpus = [
            d for d in full_corpus
            if "source_id" not in d or d["source_id"] in enabled_ids
        ]
        self._build_index()

    def enabled_source_names(self) -> list[str]:
        return [s["name"] for s in self.sources_config if s.get("enabled", True)]

    def all_sources_status(self) -> list[dict]:
        return self.sources_config

    def toggle_source(self, source_id: str, enabled: bool) -> bool:
        found = False
        for s in self.sources_config:
            if s["id"] == source_id:
                s["enabled"] = enabled
                found = True
        if found:
            save_sources_config(self.sources_config, self.sources_path)
            self.reload()
        return found

    def _build_index(self):
        self.doc_tokens = []
        df = Counter()  # document frequency لكل كلمة

        for doc in self.corpus:
            full_text = f"{doc['text']} {doc.get('topic', '')}"
            tokens = semantic_tokenize(full_text)
            self.doc_tokens.append(tokens)
            for term in set(tokens):
                df[term] += 1

        n_docs = max(len(self.corpus), 1)
        self.idf = {
            term: math.log((n_docs + 1) / (freq + 1)) + 1
            for term, freq in df.items()
        }

        self.doc_vectors = []
        for tokens in self.doc_tokens:
            self.doc_vectors.append(self._vectorize(tokens))

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        max_freq = max(tf.values()) if tf else 1
        vec = {}
        for term, freq in tf.items():
            tf_norm = freq / max_freq
            vec[term] = tf_norm * self.idf.get(term, 0.0)
        return vec

    @staticmethod
    def _cosine_sim(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        common = set(vec_a) & set(vec_b)
        dot = sum(vec_a[t] * vec_b[t] for t in common)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.05):
        query_tokens = semantic_tokenize(query)
        query_vec = self._vectorize(query_tokens)
        query_termset = set(query_tokens)

        results = []
        for doc, doc_vec, tokens in zip(self.corpus, self.doc_vectors, self.doc_tokens):
            score = self._cosine_sim(query_vec, doc_vec)
            shared_terms = query_termset & set(tokens)
            if score >= min_score:
                results.append({
                    **doc,
                    "relevance_score": round(score, 4),
                    "match_percent": round(min(score, 1.0) * 100),
                    "shared_term_count": len(shared_terms),
                })

        results.sort(key=lambda r: r["relevance_score"], reverse=True)
        return results[:top_k]


if __name__ == "__main__":
    engine = RetrievalEngine()
    # أمثلة تختبر التوحيد الدلالي: صيغة مختلفة عن الموجودة بالنص الأصلي عمداً
    for q in ["النية في العمل", "الصائمين", "الصابرين", "الجمع في السفر"]:
        print(f"\n🔍 استعلام: {q}")
        for r in engine.search(q, top_k=3):
            print(f"  [{r['match_percent']}%] {r['text'][:50]}... — {r['source_ref']}")
