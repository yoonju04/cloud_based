.PHONY: demo test repro

demo:
	python -m fts demo

test:
	pytest -q

repro:
	python -m fts repro examples/handoff/kr_discovery.json
	python -m fts repro examples/handoff/us_return.json
