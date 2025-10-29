FROM python:3.12-slim
WORKDIR /app

COPY traffic_gen/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY traffic_gen/gen.py /app/gen.py

CMD ["python","gen.py"]
