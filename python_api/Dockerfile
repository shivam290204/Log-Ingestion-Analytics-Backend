FROM python:3.11-slim

WORKDIR /app

COPY python_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY python_api/app ./app

ENV MONGO_URI=${MONGO_URI}

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
