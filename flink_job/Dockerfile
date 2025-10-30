
FROM python:3.12-slim


RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ librdkafka-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app


COPY flink_job/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


COPY flink_job/job.py /app/job.py

CMD ["python", "-u", "/app/job.py"]