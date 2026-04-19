FROM ubuntu:22.04

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /pipeline
ENV PATH="/pipeline/.venv/bin:$PATH"

COPY .python-version pyproject.toml uv.lock pipeline.py /pipeline
RUN uv sync --locked

ENTRYPOINT ["python", "pipeline.py"]