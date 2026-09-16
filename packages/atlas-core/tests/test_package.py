import atlas_core


def test_package_exposes_version():
    assert atlas_core.__version__ == "0.1.0"
