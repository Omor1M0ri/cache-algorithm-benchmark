FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: smoke test on the 10-row sample. Override for the full run:
#   docker run --rm -v "$PWD/results:/app/results" cache-benchmark scripts/run.sh full
ENTRYPOINT ["bash"]
CMD ["scripts/run.sh", "sample"]
