.PHONY: build test install clean run

# Build the Rust extractor
build:
	cd extractor && cargo build --release

# Run Python tests
test:
	source .venv/bin/activate && python3 tests/test_core.py

# Install Python package in dev mode
install:
	python3 -m venv .venv
	source .venv/bin/activate && pip install -e .

# Clean build artifacts
clean:
	cd extractor && cargo clean
	rm -rf .venv

# Extract history from a USB drive
run:
	extractor/target/release/rekord-extract $(ARGS)