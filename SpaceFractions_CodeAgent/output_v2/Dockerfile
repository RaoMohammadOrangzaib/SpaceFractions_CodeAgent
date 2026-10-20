FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source
COPY app ./app
COPY static ./static
COPY openapi.yaml internal.proto ./

# SQL and k8s artifacts for reference
COPY sql ./sql
COPY k8s ./k8s
COPY traceability_matrix.csv ./

EXPOSE 80

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
