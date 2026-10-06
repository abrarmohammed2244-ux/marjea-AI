import urllib.request, urllib.error, json

BASE = "http://127.0.0.1:5050"

def call(path, method="GET", body=None, raw=False):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        content = r.read()
        return content if raw else json.loads(content)

# الواجهة تُخدم من نفس السيرفر (سيرفر واحد، لا اعتماد على منفذ ثانٍ)
html = call("/", raw=True).decode("utf-8")
assert "<html" in html.lower(), "الصفحة الرئيسية لا تعيد HTML"
assert 'API_BASE = ""' in html, "المسار يجب أن يكون نسبياً (بدون عنوان ثابت)"
print("✅ الواجهة تُخدم من نفس السيرفر بمسار نسبي")

r = call("/api/health")
assert r["corpus_size"] > 0, r
print("✅ health:", r)

r = call("/api/sources")
assert len(r["sources"]) >= 7
print("✅ sources count:", len(r["sources"]))

r = call("/api/search", "POST", {"query": "النية في العمل"})
assert r["count"] >= 1
assert "match_percent" in r["results"][0]
assert "sources_searched" in r
print("✅ search match_percent:", r["results"][0]["match_percent"])

# اختبار البحث الدلالي: صيغة مختلفة تماماً عن النص الأصلي، لازم تلقط نتيجة
r = call("/api/search", "POST", {"query": "الصابرين"})
assert r["count"] >= 1, "البحث الدلالي يُفترض يلقط صيغة 'صبر' من استعلام 'الصابرين'"
print(f"✅ بحث دلالي (الصابرين -> صبر): {r['count']} نتيجة")

r = call("/api/search", "POST", {"query": "لا شيء يطابق هذا ابدا zzzz"})
print(f"✅ zero-match-ish query -> count: {r['count']}, sources_searched entries: {len(r['sources_searched'])}")

call("/api/sources/toggle", "POST", {"source_id": "bukhari", "enabled": False})
r_before = call("/api/search", "POST", {"query": "النية في العمل"})
call("/api/sources/toggle", "POST", {"source_id": "bukhari", "enabled": True})
r_after = call("/api/search", "POST", {"query": "النية في العمل"})
assert r_after["count"] >= r_before["count"], "توقعنا نتائج أكثر أو تساوي بعد إعادة تفعيل البخاري"
print(f"✅ toggle off bukhari -> {r_before['count']} نتيجة, toggle on -> {r_after['count']} نتيجة")

# التأكد أن endpoints المحذوفة (التحقق + القاعدة الخام) فعلياً غير موجودة
# (قد يرجع Flask 404 أو 405 حسب كيف يلتقطها route الملفات الثابتة — المهم أنها لم تعد تعمل)
for removed_path, method, body in [("/api/verify", "POST", {"text": "x"}), ("/api/corpus", "GET", None)]:
    try:
        call(removed_path, method, body)
        raise AssertionError(f"{removed_path} يُفترض محذوفاً لكنه لسه شغّال ويرجع نتيجة صحيحة")
    except urllib.error.HTTPError as e:
        assert e.code in (404, 405), f"{removed_path} أرجع {e.code} غير متوقع"
print("✅ /api/verify و /api/corpus محذوفان فعلياً (لم يعودا يعملان)")

r = call("/api/search", "POST", {"query": "النية", "synthesize": True})
assert "synthesized" in r
print("✅ synthesize mode:", r["synthesized"]["mode"])

print("\n🎉 كل الاختبارات نجحت")
