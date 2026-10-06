"""
التطبيق الرئيسي - خادم واحد يخدم الواجهة الأمامية + REST API معاً.

لماذا سيرفر واحد؟ لتفادي أي تعقيد بالمنافذ (CORS، تضارب 5000/8080...) عند مشاركة
المشروع مع آخرين للاختبار: يكفي تشغيل `python3 app.py` وفتح نفس الرابط اللي يطبعه،
سواء محلياً أو بعد نشره على استضافة عامة (Render/Railway/إلخ) — بدون أي تعديل إضافي،
لأن الواجهة تستخدم مسارات نسبية (/api/...) بدل عنوان ثابت.
"""

import os
from flask import Flask, request, jsonify, send_from_directory

from retrieval import RetrievalEngine
from evidence_classifier import classify_by_metadata
from llm_client import generate_grounded_answer

app = Flask(__name__, static_folder="static", static_url_path="")


@app.after_request
def add_cors_headers(response):
    """CORS يدوي — يبقى مفيداً حتى مع سيرفر واحد لو حد استدعى الـ API من نطاق مختلف."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


engine = RetrievalEngine()


@app.get("/")
def serve_frontend():
    """يخدم الواجهة الأمامية مباشرة من نفس السيرفر والمنفذ."""
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "corpus_size": len(engine.corpus)})


@app.post("/api/search")
def search():
    """البحث الموثوق السريع (بحث دلالي عربي: مطابقة لفظية + جذر + مرادفات)"""
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "الرجاء إدخال استعلام"}), 400

    results = engine.search(query, top_k=data.get("top_k", 5))
    for r in results:
        r["evidence"] = classify_by_metadata(r)

    matched_source_ids = {r.get("source_id") for r in results}
    response = {
        "query": query,
        "results": results,
        "count": len(results),
        # قائمة كل المصادر المفعّلة التي شملها البحث، مع تحديد أيها ظهر فيها تطابق فعلي
        "sources_searched": [
            {"name": s["name"], "matched": s["id"] in matched_source_ids}
            for s in engine.sources_config if s.get("enabled", True)
        ],
    }

    # الخطوة 5 من منهجية RAG: AI يستلم نتائج البحث ويصوغ إجابة مقيّدة بها فقط
    if data.get("synthesize"):
        response["synthesized"] = generate_grounded_answer(query, results)

    return jsonify(response)


@app.get("/api/sources")
def list_sources():
    """لوحة المصادر: عرض كل مجموعات المصادر وحالتها (مفعّل/معطّل)"""
    return jsonify({"sources": engine.all_sources_status()})


@app.post("/api/sources/toggle")
def toggle_source():
    """لوحة المصادر: تفعيل أو تعطيل مجموعة مصدر بعينها"""
    data = request.get_json(force=True)
    source_id = data.get("source_id")
    enabled = data.get("enabled")
    if source_id is None or enabled is None:
        return jsonify({"error": "الرجاء تحديد source_id و enabled"}), 400

    found = engine.toggle_source(source_id, bool(enabled))
    if not found:
        return jsonify({"error": "المصدر غير موجود"}), 404

    return jsonify({"sources": engine.all_sources_status(), "corpus_size": len(engine.corpus)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    # threaded=True: لو أكثر من عضو لجنة فتح الرابط بنفس الوقت، كل طلب يُخدم بخيط
    # مستقل بدل الانتظار بالتسلسل على خيط واحد (مهم عند الاستضافة لجلسة تحكيم جماعية).
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False, threaded=True)
