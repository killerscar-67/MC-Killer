FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MCK_DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-tra libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY mcmark ./mcmark
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 marker && mkdir /data && chown marker:marker /data
USER marker
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
ENTRYPOINT ["python", "-m", "mcmark.web"]
CMD ["serve", "--host", "0.0.0.0", "--data", "/data", "--port", "8000"]
