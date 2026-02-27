FROM python:3.12-slim
WORKDIR /app
COPY monitor.py .
RUN mkdir -p /data
VOLUME /data
CMD ["python3", "-u", "monitor.py"]
