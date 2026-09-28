# Convenience targets (Windows users: run the python commands shown in README).
PY ?= python

.PHONY: all data pipeline dashboard sql notebooks docs test

all: pipeline sql notebooks docs test

data:            ## Download the current NYC Open Data release
	$(PY) scripts/download_data.py

pipeline:        ## Clean, aggregate, analyse, forecast; writes data/processed and reports
	PYTHONPATH=src $(PY) -m nycha_energy.pipeline

dashboard:       ## Rebuild docs/index.html from data/processed (the pipeline also does this)
	PYTHONPATH=src $(PY) -m nycha_energy.dashboard

sql:             ## Rebuild the SQL layer in DuckDB and run validation + reconciliation
	$(PY) scripts/run_sql.py

notebooks:       ## Re-execute notebooks in place
	cd notebooks && for nb in 0*.ipynb; do $(PY) -m jupyter nbconvert --to notebook --execute --inplace $$nb; done

docs:            ## Regenerate the data dictionary
	$(PY) scripts/build_data_dictionary.py

test:            ## Unit tests (no data required)
	$(PY) -m pytest -q
