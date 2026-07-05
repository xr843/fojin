"""Root pytest conftest (loaded before tests/ and tests_integration/).

app.config now treats an unset FOJIN_ENV as production and fail-fasts without
strong secrets. Tests run without those secrets, so declare the dev
environment before anything imports app.config. Must stay at the rootdir so it
applies to every test suite under backend/.
"""

import os

os.environ.setdefault("FOJIN_ENV", "development")
