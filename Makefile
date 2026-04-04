.PHONY: setup run demo kill clean test

# Install dependencies and make the script executable
setup:
	@echo "==> Setting up TerminalRescue environment..."
	chmod +x run_demo.sh setup_foxmq.sh
	python3 -m venv venv
	venv/bin/pip install -r requirements.txt
	./setup_foxmq.sh
	@echo "==> Setup complete! Run 'make run' to start."

# Run the simulation
run:
	./run_demo.sh

# Alias for run
demo: run

# Force kill any stuck background processes (FoxMQ or Drones)
kill:
	@echo "==> Terminating rogue processes..."
	-killall foxmq python3 2>/dev/null
	@echo "==> Clean."

# Deep clean 
clean: kill
	@echo "==> Removing cache files..."
	rm -rf __pycache__ .pytest_cache *.pyc

# Run test suite with coverage
test:
	venv/bin/pytest --cov=. --cov-report=term-missing --cov-fail-under=100
