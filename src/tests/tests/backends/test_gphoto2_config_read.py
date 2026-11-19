from unittest.mock import MagicMock, patch

import pytest

try:
    from photobooth.services.backends.gphoto2 import ConfigReadRequest, Gphoto2Backend
except ImportError:
    pytest.skip(reason="gphoto2 not available", allow_module_level=True)

from photobooth.services.config.groups.cameras import GroupCameraGphoto2


@pytest.fixture
def backend():
    backend = Gphoto2Backend(GroupCameraGphoto2())
    backend._camera = MagicMock()
    backend._camera.get_port_info.return_value.get_path.return_value = "usb:001,005"
    return backend


def _detected(cameras):
    """Replace gphoto2 in the backend module, the real Camera.autodetect is read-only."""
    gp_mock = MagicMock()
    gp_mock.Camera.autodetect.return_value = cameras
    return patch("photobooth.services.backends.gphoto2.gp", gp_mock)


def _queue_request(backend: Gphoto2Backend) -> ConfigReadRequest:
    req = ConfigReadRequest()
    backend._config_read_requests.append(req)
    return req


def test_config_read_while_camera_connected(backend: Gphoto2Backend):
    req = _queue_request(backend)

    with (
        _detected([("Canon EOS 450D", "usb:001,005")]),
        patch("photobooth.services.backends.gphoto2.camera_config_from_widget", return_value="config") as from_widget,
    ):
        backend._process_config_read_requests()

    assert req.done.is_set()
    assert req.error is None
    assert req.result == "config"
    from_widget.assert_called_once()


def test_config_read_after_camera_was_unplugged(backend: Gphoto2Backend):
    """A camera unplugged or switched off in standby must not be answered from the libgphoto2 cache."""
    req = _queue_request(backend)

    with _detected([]):
        # the worker loop is left, so the supervisor reconnects once the camera is back
        with pytest.raises(RuntimeError):
            backend._process_config_read_requests()

    assert req.done.is_set()
    assert isinstance(req.error, ConnectionError)
    assert req.result is None
    backend._camera.get_config.assert_not_called()


def test_config_read_camera_replugged_on_other_port(backend: Gphoto2Backend):
    req = _queue_request(backend)

    with _detected([("Canon EOS 450D", "usb:001,006")]):
        with pytest.raises(RuntimeError):
            backend._process_config_read_requests()

    assert isinstance(req.error, ConnectionError)


def test_no_bus_check_without_requests(backend: Gphoto2Backend):
    with _detected([]) as gp_mock:
        backend._process_config_read_requests()

    gp_mock.Camera.autodetect.assert_not_called()
