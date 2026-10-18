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
RUN chmod +x start.sh && mkdir -p /data && chmod -R a+rwX /app /data

USER 1000
ENV PORT=7860 FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379 HOME=/tmp
EXPOSE 7860
ENTRYPOINT []
CMD ["/app/start.sh"]
