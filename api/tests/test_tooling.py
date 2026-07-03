import app


def test_api_package_is_importable() -> None:
    assert app.__name__ == "app"
