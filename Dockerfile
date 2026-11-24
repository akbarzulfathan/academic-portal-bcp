FROM python:3.11-slim

WORKDIR /code

# Instal dependensi sistem ringan
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app

# Default environment (akan ditimpa oleh IaC per Region di Azure Container Apps)
ENV REGION_NAME="southeastasia"
ENV USE_MOCK="false"
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
