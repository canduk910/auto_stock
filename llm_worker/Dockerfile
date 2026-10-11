FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lw/ ./lw/

RUN useradd --create-home --uid 1000 --user-group llm
USER llm

ENTRYPOINT ["python", "-m", "lw"]
