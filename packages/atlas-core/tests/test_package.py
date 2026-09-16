from importlib.metadata import version

import atlas_core


def test_package_version_matches_distribution():
    assert atlas_core.__version__ == version("atlas-kit")
