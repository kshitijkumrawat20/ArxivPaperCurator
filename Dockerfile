## TWO STAGE DOCKERFILE FOR PRODUCTION DEPLOYMENT ##

## The multi-stage build keeps the final image small - you build and install in the first stage, then copy only what you need to a clean image. This removes build tools you don't need at runtime.

# Build stage
# Using Astral's UV image with Python 3.13 and Debian Bookworm
FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS base

# Set the working directory in the container to /app
WORKDIR /app 

# Copy the pyproject.toml and uv.lock files to the container
COPY pyproject.toml uv.lock ./

# Set environment variables for UV
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

#intall deps 
RUN --mount=type=cache,target=/root/.cache/uv \  
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --frozen --no-dev

    
# Copy the rest of the application code to the container
COPY src /app/src  

# Final stage
# 
FROM python:3.13-slim-bookworm AS final
# Expose port 8000 for the fastapi application
EXPOSE 8000

# Set environment variables for the application
ENV PYTHONUNBUFFERED=1

# Set the version of the application
ARG VERSION=0.1.0

ENV APP_VERSION=${VERSION}

WORKDIR /app
COPY --from=base /app /app

ENV PATH="/app/.venv/bin:$PATH"

# Run the application 
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]


