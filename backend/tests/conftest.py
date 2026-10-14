import pytest
from filtervisual.config.schema import default_experiment


@pytest.fixture
def baseline_config():
    return default_experiment()
