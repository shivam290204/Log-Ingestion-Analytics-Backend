FROM python:3.11-slim

WORKDIR /app

# requirements install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code copy
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
