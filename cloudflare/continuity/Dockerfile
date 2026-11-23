# Imagem de continuidade do Heimdall (linux/amd64). Contexto de construção: a raiz do repositório (ver wrangler.jsonc).
FROM --platform=linux/amd64 python:3.12-slim
ENV PYTHONUNBUFFERED=1 HEIMDALL_CONTINUIDADE_MODO=1
WORKDIR /app
COPY cloudflare/continuity/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app
COPY cloudflare/continuity/entrada.py /app/entrada.py
EXPOSE 8080
CMD ["python3", "/app/entrada.py"]
