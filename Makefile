.PHONY: setup run demo kill clean

# Install dependencies and make the script executable
setup:
	@echo "==> Setting up TerminalRescue environment..."
	chmod +x run_demo.sh drone.py grid_display.py
	python3 -m pip install -r requirements.txt
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
