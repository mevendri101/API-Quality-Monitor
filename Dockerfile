FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY monitor ./monitor
RUN pip install --no-cache-dir . && useradd --create-home app && mkdir /data && chown app:app /data
USER app
ENV MONITOR_DB=/data/monitor.db
EXPOSE 8000
CMD ["uvicorn", "monitor.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
