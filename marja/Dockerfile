# Dockerfile لاستضافة "مرجع" على Hugging Face Spaces (Docker SDK)
# يبني من backend/ فقط لأن الواجهة (static/) أصلاً جزء منه ويُخدمان بسيرفر واحد.

FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Hugging Face Spaces تتوقع أن يستمع التطبيق على منفذ 7860 افتراضياً
ENV PORT=7860
EXPOSE 7860

CMD ["python3", "app.py"]
