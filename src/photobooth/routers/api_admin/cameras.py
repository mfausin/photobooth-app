import logging

from fastapi import APIRouter, HTTPException, status

from ...container import container
from ...services.backends.gphoto2_config import Gphoto2CameraConfig
from ...utils.enumerate import enumerate_lock
from ...utils.exceptions import BackendNotRunning

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cameras", tags=["admin", "cameras"])


@router.get("/gphoto2/{config_index}/config")
def api_get_gphoto2_camera_config(config_index: int) -> Gphoto2CameraConfig:
    """Read parameters, current values and allowed choices from the connected gphoto2 camera.

    config_index is the index of the backend in the cameras config (group_backends). If that backend is running,
    the camera is read through it. If no gphoto2 backend is running, the camera is opened directly for the read.
    """
    try:
        from ...services.backends.gphoto2 import Gphoto2Backend, read_camera_config_once
    except ImportError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, f"gphoto2 is not available on this system: {exc}") from exc

    backend = container.acquisition_service.get_backend_by_config_index(config_index)

    try:
        if isinstance(backend, Gphoto2Backend):
            return backend.read_camera_config()

        if any(isinstance(other, Gphoto2Backend) for other in container.acquisition_service.get_backends()):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Another gphoto2 backend is using the camera. Read the config from that backend instead.",
            )

        with enumerate_lock:
            return read_camera_config_once()

    except HTTPException:
        raise
    except (BackendNotRunning, ConnectionError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"No camera connected or camera not ready: {exc}") from exc
    except TimeoutError as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, f"Camera did not respond: {exc}") from exc
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Could not read the camera config: {exc}") from exc
