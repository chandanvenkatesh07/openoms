FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY openoms ./openoms
RUN pip install --upgrade pip && pip install .
CMD ["python", "-m", "openoms.server"]
