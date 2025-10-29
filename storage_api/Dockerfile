FROM python:3.12-slim
WORKDIR /app

# Dependen cias
COPY storage_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY storage_api/main.py /app/main.py
COPY common/schema.py /app/schema.py

EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
