FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

COPY . .
RUN chmod +x /app/scripts/trigger_ballot.sh

EXPOSE 5000

CMD ["python", "ballot_audits.py"]
