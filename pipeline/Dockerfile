FROM python:3.13.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /pipeline

COPY .python-version uv.lock pyproject.toml pipeline.py README.md ./
COPY src /pipeline/src/
RUN uv sync --locked

ENV PATH="/pipeline/.venv/bin:$PATH"

# RUN uv sync

ENTRYPOINT ["python3","pipeline.py"]