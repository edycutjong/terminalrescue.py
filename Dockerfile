# Stage 1: Build the Rust Vertex Native Drone binary
FROM rust:slim AS builder
WORKDIR /app
# We only copy the vertex_drone directory to build the Rust components efficiently
COPY vertex_drone ./vertex_drone
RUN cd vertex_drone && cargo build --release

# Stage 2: Final runtime wrapper with lightweight Python
FROM python:3.11-slim
WORKDIR /app

# Install dependencies required by the UI
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all the standard application code (FastAPI, static files, etc)
COPY . .

# Copy the compiled Rust binary from the builder stage into the correct expected folder
COPY --from=builder /app/vertex_drone/target/release/vertex_drone ./vertex_drone/target/release/vertex_drone

# Make run_demo.sh cleanly executable (optional, since we invoke uvicorn directly below)
RUN chmod +x run_demo.sh

# Expose FastAPI interface
EXPOSE 8000

# We don't use run_demo.sh here because it attempts to spawn a local MacOS browser via 'open'
CMD ["python", "-m", "uvicorn", "web_ui:app", "--host", "0.0.0.0", "--port", "8000"]
