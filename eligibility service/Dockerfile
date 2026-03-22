FROM python:3-slim

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ./document_service.py .

CMD ["python", "document_service.py"]
