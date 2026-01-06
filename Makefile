clean:

	rm -rf dist/ build/ *.egg-info

build:

	python3 -m build

twine-upload:

	twine upload dist/*