# ⚠️ ملاحظة: الملف ده ما اتجرّبش فعليًا (معنديش Docker في بيئة التطوير)، بس بسيط ومبني على أنماط معروفة.
FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server server
COPY webapp webapp
# مسار التخزين الدائم (اربط عليه volume في الاستضافة)
ENV DATA_DIR=/data
EXPOSE 8080
WORKDIR /app/server
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
