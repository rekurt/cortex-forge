FROM python:3.12-slim
RUN useradd -r -s /usr/sbin/nologin app && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY proxy.py .
VOLUME ["/data"]
USER app
CMD ["python3", "-u", "proxy.py"]
