FROM python:3.14-slim
# Create non-root user. Container starts as root so proxy.py can fix /data ownership
# on existing volumes (migration from old root-owned volumes), then drops to 'app'.
RUN useradd -r -s /usr/sbin/nologin app && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY proxy.py .
VOLUME ["/data"]
# Note: no USER directive — proxy.py calls _drop_privileges() at startup
CMD ["python3", "-u", "proxy.py"]
