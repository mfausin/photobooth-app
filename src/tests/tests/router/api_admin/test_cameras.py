import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from photobooth.container import container
from photobooth.services.backends.gphoto2_config import Gphoto2CameraConfig
from photobooth.utils.exceptions import BackendNotRunning

logger = logging.getLogger(name=None)

gphoto2_backend_module = pytest.importorskip("photobooth.services.backends.gphoto2")


def test_admin_cameras_gphoto2_config_from_running_backend(client_authenticated: TestClient):
    backend = MagicMock(spec=gphoto2_backend_module.Gphoto2Backend)
    backend.read_camera_config.return_value = Gphoto2CameraConfig(model="Test Cam")

    with patch.object(container.acquisition_service, "get_backend_by_config_index", return_value=backend):
        response = client_authenticated.get("/admin/cameras/gphoto2/0/config")

    assert response.status_code == 200
    assert response.json()["model"] == "Test Cam"


def test_admin_cameras_gphoto2_config_backend_not_connected(client_authenticated: TestClient):
    backend = MagicMock(spec=gphoto2_backend_module.Gphoto2Backend)
    backend.read_camera_config.side_effect = BackendNotRunning("camera is not connected")

    with patch.object(container.acquisition_service, "get_backend_by_config_index", return_value=backend):
        response = client_authenticated.get("/admin/cameras/gphoto2/0/config")

    assert response.status_code == 503


def test_admin_cameras_gphoto2_config_conflict_with_other_backend(client_authenticated: TestClient):
    other = MagicMock(spec=gphoto2_backend_module.Gphoto2Backend)

    with (
        patch.object(container.acquisition_service, "get_backend_by_config_index", return_value=None),
        patch.object(container.acquisition_service, "get_backends", return_value=[other]),
    ):
        response = client_authenticated.get("/admin/cameras/gphoto2/5/config")

    assert response.status_code == 409


def test_admin_cameras_gphoto2_config_direct_read_without_camera(client_authenticated: TestClient):
    with (
        patch.object(container.acquisition_service, "get_backend_by_config_index", return_value=None),
        patch.object(container.acquisition_service, "get_backends", return_value=[]),
        patch.object(gphoto2_backend_module, "read_camera_config_once", side_effect=ConnectionError("no camera")),
    ):
        response = client_authenticated.get("/admin/cameras/gphoto2/0/config")

    assert response.status_code == 503


def test_admin_cameras_gphoto2_config_direct_read(client_authenticated: TestClient):
    with (
        patch.object(container.acquisition_service, "get_backend_by_config_index", return_value=None),
        patch.object(container.acquisition_service, "get_backends", return_value=[]),
        patch.object(gphoto2_backend_module, "read_camera_config_once", return_value=Gphoto2CameraConfig(model="Direct")),
    ):
        response = client_authenticated.get("/admin/cameras/gphoto2/0/config")

    assert response.status_code == 200
    assert response.json()["model"] == "Direct"
