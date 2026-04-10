.PHONY: setup run demo kill clean test docker-build docker-run compose-up compose-down compose-clean

# Default simulation parameters (can be overridden via CLI: make run GRID_X=20 GRID_Y=20 DRONE_COUNT=30)
GRID_X ?= 10
GRID_Y ?= 10
DRONE_COUNT ?= 10
# Install dependencies and make the script executable
setup:
	@echo "==> Setting up TerminalRescue environment..."
	chmod +x run_demo.sh
	python3 -m venv venv
	venv/bin/pip install -r requirements.txt
	@echo "==> Compiling Vertex 2.0 Native Rust Drone..."
	cd vertex_drone && cargo build --release
	@echo "==> Setup complete! Run 'make run' to start."

# Run the simulation
run:
	GRID_X=$(GRID_X) GRID_Y=$(GRID_Y) DRONE_COUNT=$(DRONE_COUNT) ./run_demo.sh

# Run massive 400 sector simulation shortcut
run-massive:
	GRID_X=20 GRID_Y=20 DRONE_COUNT=78 ./run_demo.sh

# Alias for run
demo: run

# Force kill any stuck background processes (FoxMQ or Drones)
kill:
	@echo "==> Terminating rogue processes..."
	-killall vertex_drone python3 2>/dev/null
	@echo "==> Clean."

# Deep clean 
clean: kill
	@echo "==> Removing cache files..."
	rm -rf __pycache__ .pytest_cache *.pyc
	rm -rf vertex_drone/target

# Run test suite
test:
	venv/bin/pytest tests -v

# Build the Docker image natively
docker-build:
	@echo "==> Building TerminalRescue Docker Image (Multi-stage Rust + Python)..."
	docker build -t terminal-rescue-vertex .

# Run the project via Docker container
docker-run:
	@echo "==> Booting TerminalRescue inside Docker (Port 8000)..."
	docker run -p 8000:8000 -it --rm terminal-rescue-vertex

# Run the full distributed 6-container simulation via docker-compose
compose-up: docker-build
	@echo "==> Booting 6-container distributed mesh simulation..."
	docker-compose up -d

# Spin down the 6-container cluster
compose-down:
	docker-compose down

# Destroy the cluster, volumes, and built images
compose-clean:
	@echo "==> Destroying cluster and removing Docker images..."
	docker-compose down -v --rmi all
