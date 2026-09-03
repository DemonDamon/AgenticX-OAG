PYTHON ?= .venv/bin/python
GEN_DIR := agenticx_oag/contracts/gen
PROTOS := $(shell find proto -name '*.proto' 2>/dev/null)

.PHONY: proto test lint dev-up dev-down

# Generate Python protobuf bindings into contracts/gen, flattened to <pkg>_<ver>_pb2.py
# and with cross-proto imports rewritten to gen-internal relative imports (idempotent).
proto:
	$(PYTHON) -m grpc_tools.protoc -I proto \
		--python_out=$(GEN_DIR) \
		$(PROTOS)
	@set -e; \
	for f in $$(find $(GEN_DIR)/agenticx_oag -name '*_pb2.py' 2>/dev/null); do \
		rel=$${f#$(GEN_DIR)/agenticx_oag/}; \
		pkg=$$(dirname "$$rel" | tr '/' '_'); \
		mv "$$f" "$(GEN_DIR)/$${pkg}_pb2.py"; \
	done; \
	rm -rf $(GEN_DIR)/agenticx_oag; \
	perl -pi -e 's/^import agenticx_oag(?:\.[A-Za-z0-9_]+)*\.([A-Za-z0-9_]+_pb2) as (.+)$$/from . import $$1 as $$2/; s/^from agenticx_oag(?:\.[A-Za-z0-9_]+)* import ([A-Za-z0-9_]+_pb2)( as .+)?$$/from . import $$1$$2/' $(GEN_DIR)/*_pb2.py

test:
	$(PYTHON) -m pytest tests/ -m "not integration"

lint:
	$(PYTHON) -m ruff check agenticx_oag tests
	$(PYTHON) -m mypy agenticx_oag

dev-up:
	docker compose -f docker-compose.dev.yml up -d

dev-down:
	docker compose -f docker-compose.dev.yml down
