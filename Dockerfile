                                                                                                                      
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PRELOAD_RAG_ON_STARTUP=false \
    PRELOAD_NOISE_REMOVER_ON_STARTUP=false \
    TOKENIZERS_PARALLELISM=false

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

VOLUME /data

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
