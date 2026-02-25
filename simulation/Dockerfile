FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install the project and all dependency groups
RUN uv sync --all-groups --no-dev

# Copy simulation configs (overridden per service via volume mounts)
COPY configs/ configs/

# Default: run the daemon
CMD ["uv", "run", "master-control", "--config-dir", "configs", "up"]
