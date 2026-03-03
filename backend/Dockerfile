FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y texlive-latex-base texlive-latex-extra && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY start.sh ./start.sh
COPY app ./app

RUN chmod +x ./start.sh

CMD ["./start.sh"]
