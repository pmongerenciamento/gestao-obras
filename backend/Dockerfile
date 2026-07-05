FROM python:3.11-slim

# Instalar Java 17 para o MPXJ
RUN apt-get update && apt-get install -y \
    default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PORT=8000

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
