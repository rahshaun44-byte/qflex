# Stage 1: Build dependencies
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Final hardened image
FROM python:3.11-slim

# Create a non-root user with known UID/GID FIRST
# WHY: /root/.local is locked to root. USER 1000 cannot read it.
# Solution: create real user, copy packages to THEIR home directory.
RUN groupadd -g 1000 amara && useradd -u 1000 -g amara -m -s /bin/bash amara

WORKDIR /app

# Copy installed packages to the non-root user's home — not root's
COPY --from=builder /root/.local /home/amara/.local

# Copy app files with correct ownership
COPY --chown=amara:amara . .

ENV PATH=/home/amara/.local/bin:$PATH

USER 1000

CMD ["python", "amara_mcp.py"]
