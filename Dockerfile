FROM python:3.9-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /root/.postgresql && \
    curl -f -o /root/.postgresql/root.crt "https://storage.yandexcloud.net/cloud-certs/CA.pem" && \
    chmod 0644 /root/.postgresql/root.crt

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY key.json /app/key.json

CMD ["python", "app.py"]