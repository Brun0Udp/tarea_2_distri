FROM python:3.12-slim
WORKDIR /app

COPY llm_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY llm_worker/worker.py /app/worker.py
COPY common/schema.py /app/schema.py

CMD ["python","worker.py"]
