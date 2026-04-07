test:
	poetry run pytest -vv -m "not stress"

test-integration:
	poetry run pytest -vv -m integration

test-stress:
	poetry run pytest -vv -m stress

test-all:
	poetry run pytest -vv

