# FROM python:3.11

# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# COPY app ./app
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Example: backend/Dockerfile

FROM python:3.11-slim

# Add pdflatex dependency
RUN apt-get update && \
    apt-get install -y texlive-latex-base && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Rest of your setup
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
