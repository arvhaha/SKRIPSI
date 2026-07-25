FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TF_CPP_MIN_LOG_LEVEL=2

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/bootstrap-data && \
    cp -f /app/Master_Data_Spasial_Jaktim_1990_sekarang.csv /app/bootstrap-data/Master_Data_Spasial_Jaktim_1990_sekarang.csv && \
    cp -f /app/data/drainase_jaktim_template_backend.csv /app/bootstrap-data/drainase_jaktim_template_backend.csv && \
    cp -f /app/data/drainase_jaktim_bersih.csv /app/bootstrap-data/drainase_jaktim_bersih.csv && \
    cp -f /app/data/drainase_jaktim_ringkasan_kecamatan.csv /app/bootstrap-data/drainase_jaktim_ringkasan_kecamatan.csv && \
    cp -f /app/data/east-jakarta-template.json /app/bootstrap-data/east-jakarta-template.json && \
    cp -f /app/data/jkt.geojson /app/bootstrap-data/jkt.geojson

EXPOSE 8000

CMD ["python", "backend_fastapi/run.py"]
