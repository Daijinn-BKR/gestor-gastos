import pytest

from gestor import create_app


@pytest.fixture
def app(tmp_path):
    # Cada test usa su propia base de datos temporal: nunca toca tus datos reales.
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})


@pytest.fixture
def client(app):
    return app.test_client()
