import os

import pytest

@pytest.fixture('session')
def test_data_dir():
    return os.path.join(os.path.dirname(__file__), 'data')
