.PHONY: help sim sim-docker sim-docker-down sim-tunnel seed

help:
	@echo "Targets:"
	@echo "  sim              run sim locally (uv) — single CLI scenario"
	@echo "  sim-docker       build + run sim in Docker (FastAPI on :8000)"
	@echo "  sim-docker-down  stop the Docker sim service"
	@echo "  sim-tunnel       expose local :8000 via cloudflared (HTTPS URL)"
	@echo "  seed             regenerate the committed historian fallback"

sim:
	cd sim && uv run copilot-sim run barcelona-baseline.yaml

sim-docker:
	docker compose up --build sim

sim-docker-down:
	docker compose down

sim-tunnel:
	cloudflared tunnel --url http://localhost:8000

seed:
	cd sim && uv run copilot-sim run barcelona-baseline.yaml --db-path ../data/historian.sqlite
