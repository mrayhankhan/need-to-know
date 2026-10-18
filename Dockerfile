# One container with FalkorDB and the app, for Hugging Face Spaces (port 7860) or local use.
FROM falkordb/falkordb:latest

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ntk ./ntk
COPY web ./web
COPY start.sh .
RUN find / -xdev -name 'falkordb.so' 2>/dev/null | head -1 > /app/.falkordb_module \
 && (command -v redis-server || find / -xdev -name redis-server -type f 2>/dev/null | head -1) > /app/.redis_server \
 && cat /app/.falkordb_module /app/.redis_server \
 && chmod +x start.sh \
 && (id -u 1000 >/dev/null 2>&1 || useradd -m -u 1000 user) \
 && mkdir -p /data && chown -R 1000:1000 /app /data

USER 1000
ENV PORT=7860 FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379
EXPOSE 7860
ENTRYPOINT []
CMD ["/app/start.sh"]
