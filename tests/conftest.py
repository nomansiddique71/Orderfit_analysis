"""Keep the test suite deterministic: never call Gemini from tests."""

import os

os.environ["ORDERFIT_OFFLINE"] = "1"
