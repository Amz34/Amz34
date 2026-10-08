.PHONY: test check lint clean

test:
	python3 -m unittest discover -s tests -v

check:
	python3 tools/check_profile.py README.md

lint:
	python3 -m py_compile tools/check_profile.py tests/test_check_profile.py
	@echo "py_compile OK"

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache
