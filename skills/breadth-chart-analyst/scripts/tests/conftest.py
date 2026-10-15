"""
Pytest fixtures for breadth-chart-analyst tests.
"""

import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))


@pytest.fixture
def sample_uptrend_chart():
    """Path to the sample Uptrend Ratio chart in assets."""
    chart_path = (
        Path(__file__).parent.parent.parent / "assets" / "US_Stock_Market_Uptrend_Ratio.jpeg"
    )
    if not chart_path.exists():
        pytest.skip(f"Sample chart not found: {chart_path}")
    return str(chart_path)


@pytest.fixture
def sample_breadth_chart():
    """Path to the sample S&P 500 Breadth Index chart in assets."""
    chart_path = (
        Path(__file__).parent.parent.parent / "assets" / "SP500_Breadth_Index_200MA_8MA.jpeg"
    )
    if not chart_path.exists():
        pytest.skip(f"Sample chart not found: {chart_path}")
    return str(chart_path)


@pytest.fixture
def test_data_dir():
    """Directory for test data files."""
    return Path(__file__).parent / "test_data" / "uptrend_ratio_samples"


@pytest.fixture
def nonexistent_image():
    """Path to a file that doesn't exist (for error handling tests)."""
    return "/nonexistent/path/to/image.jpeg"


@pytest.fixture
def scripts_dir():
    """Path to the scripts directory."""
    return Path(__file__).parent.parent / "scripts"
