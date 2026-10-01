FROM python:3.12-slim

WORKDIR /app

RUN mkdir -p /root/.streamlit && \
    printf '[general]\nemail = ""\n' > /root/.streamlit/credentials.toml

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8501

# Entrypoint imports on-disk drafts (idempotent) then starts the app.
CMD ["./docker-entrypoint.sh"]
