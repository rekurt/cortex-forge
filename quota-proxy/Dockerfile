FROM python:3.12-slim
WORKDIR /app
COPY proxy.py .
RUN mkdir -p /data
VOLUME ["/data"]
CMD ["python3", "-u", "proxy.py"]
