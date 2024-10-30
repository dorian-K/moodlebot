FROM python:3.10-slim

RUN apt-get update && apt-get install -y cron tzdata

ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY main.py /usr/local/bin/script.py

COPY crontab /etc/cron.d/my-cron-job

RUN chmod 0644 /etc/cron.d/my-cron-job

RUN crontab /etc/cron.d/my-cron-job

CMD ["cron", "-f"]