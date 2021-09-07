.PHONY: build

build:
	python3 -m build

upload-testpypy:
	python3 -m twine upload --repository testpypy dist/*

upload-pypy:
	python3 -m twine upload dist/*
