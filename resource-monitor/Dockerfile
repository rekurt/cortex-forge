FROM python:3.14-slim
RUN useradd -r -s /usr/sbin/nologin app
WORKDIR /app
COPY monitor.py .
RUN mkdir -p /data && chown app:app /data
VOLUME /data
USER app
CMD ["python3", "-u", "monitor.py"]
