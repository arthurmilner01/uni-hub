FROM python:3.12

ENV PYTHONUNBUFFERED=1

WORKDIR /uni_hub

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000