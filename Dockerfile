FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY analyzer.py main.py ./
# Cloud Run sets $PORT. --no-access-log keeps request lines out of the logs.
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log
