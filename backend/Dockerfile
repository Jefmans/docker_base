FROM python:latest

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# FROM python:3.11-slim

# # Avoid interactive prompts
# ENV DEBIAN_FRONTEND=noninteractive

# # Install system dependencies
# RUN apt-get update && apt-get install -y \
#     build-essential gcc libpq-dev curl \
#     && rm -rf /var/lib/apt/lists/*

# # Set working directory
# WORKDIR /app

# # Copy and install Python requirements
# COPY requirements.txt .
# RUN pip install --upgrade pip
# RUN pip install --prefer-binary --no-cache-dir -r requirements.txt

# # Copy application code
# COPY app ./app

# # Start the FastAPI server
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
