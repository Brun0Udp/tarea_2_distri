# ./flink_job/Dockerfile
FROM python:3.12-slim

# Necesario para confluent-kafka
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ librdkafka-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias Python
COPY flink_job/requirements.txt .
# Asegúrate que requirements.txt contenga al menos: confluent-kafka
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY flink_job/job.py /app/job.py

CMD ["python", "-u", "/app/job.py"]