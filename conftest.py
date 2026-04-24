from pathlib import Path


def pytest_ignore_collect(collection_path, config):
    if (
        "omnidapter-sdk" in collection_path.parts
        and not Path("omnidapter-sdk/omnidapter_sdk/api").exists()
    ):
        return True
