"""
Read the configuration of a gphoto2 camera into plain data, so the admin UI can offer the parameters and values
the connected camera actually supports.

The module does not import gphoto2 itself, it only works on the widget objects gphoto2 hands out. That keeps it
importable (and testable) on platforms without gphoto2.
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# libgphoto2 widget types (CameraWidgetType), stable since libgphoto2 2.4
WIDGET_TYPES: dict[int, str] = {
    0: "window",
    1: "section",
    2: "text",
    3: "range",
    4: "toggle",
    5: "radio",
    6: "menu",
    7: "button",
    8: "date",
}

# widget types the gphoto2 backend can set (see Gphoto2Backend._update_camera_config)
SETTABLE_TYPES = ("text", "toggle", "radio", "menu")

# names that hold the exposure mode (auto, P, Tv, Av, M, ...) depending on the camera driver.
# the first one found wins, so the more specific names come first.
EXPOSURE_MODE_NAMES = (
    "autoexposuremodedial",  # Canon EOS, newer models (mode dial)
    "autoexposuremode",  # Canon EOS
    "expprogram",  # Nikon, Sony, Fuji, Olympus, Panasonic and generic PTP
    "exposuremode",
    "exposureprogram",
    "shootingmode",  # Canon PowerShot
)

WidgetType = Literal["text", "range", "toggle", "radio", "menu", "button", "date", "unknown"]


class Gphoto2ConfigWidget(BaseModel):
    """One camera parameter as reported by the camera."""

    name: str = Field(description="Name to use in the parameter sets, e.g. 'iso'.")
    label: str = Field(description="Human readable label reported by the camera driver (language depends on the system locale).")
    section: str = Field(description="Label of the section the parameter belongs to, e.g. 'Capture Settings'.")
    type: WidgetType
    readonly: bool
    settable: bool = Field(description="True if the app can set this parameter (writable and a supported type).")
    value: str = Field(description="Current value, converted to text the same way it is entered in the parameter sets.")
    choices: list[str] = Field(default_factory=list, description="Allowed values for radio and menu parameters in the camera's current mode.")
    range_min: float | None = None
    range_max: float | None = None
    range_step: float | None = None


class Gphoto2CameraConfig(BaseModel):
    """Configuration of the connected camera at the time it was read."""

    model: str | None = Field(default=None, description="Camera model, if the camera reports it.")
    mode: Gphoto2ConfigWidget | None = Field(
        default=None,
        description="Parameter holding the exposure mode (e.g. Manual, Av, Tv). None if the camera has no known mode parameter.",
    )
    widgets: list[Gphoto2ConfigWidget] = Field(default_factory=list)


# gphoto2.CameraWidget, typed loosely so the module works without gphoto2 and with test doubles
_Widget = Any


def _children(widget: _Widget):
    for index in range(widget.count_children()):
        yield widget.get_child(index)


def _value_to_str(value: Any, widget_type: str) -> str:
    if value is None:
        return ""
    if widget_type == "toggle":
        # gphoto2 reports toggles as int, 2 means unknown on some drivers
        return str(int(value))
    if widget_type == "range" and isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _convert_widget(widget: _Widget, section: str) -> Gphoto2ConfigWidget:
    widget_type = WIDGET_TYPES.get(widget.get_type(), "unknown")
    readonly = bool(widget.get_readonly())

    try:
        value = _value_to_str(widget.get_value(), widget_type)
    except Exception as exc:  # some drivers fail to report values of single widgets, keep the rest
        logger.debug(f"cannot read value of '{widget.get_name()}': {exc}")
        value = ""

    converted = Gphoto2ConfigWidget(
        name=widget.get_name(),
        label=widget.get_label(),
        section=section,
        type=widget_type,  # pyrefly: ignore [bad-argument-type]
        readonly=readonly,
        settable=(not readonly) and widget_type in SETTABLE_TYPES,
        value=value,
    )

    if widget_type in ("radio", "menu"):
        try:
            converted.choices = [str(choice) for choice in widget.get_choices()]
        except Exception as exc:
            logger.debug(f"cannot read choices of '{converted.name}': {exc}")
    elif widget_type == "range":
        try:
            converted.range_min, converted.range_max, converted.range_step = widget.get_range()
        except Exception as exc:
            logger.debug(f"cannot read range of '{converted.name}': {exc}")

    return converted


def _collect(widget: _Widget, section: str, out: list[Gphoto2ConfigWidget]) -> None:
    for child in _children(widget):
        widget_type = WIDGET_TYPES.get(child.get_type(), "unknown")
        if widget_type in ("section", "window"):
            _collect(child, child.get_label() or child.get_name(), out)
        else:
            out.append(_convert_widget(child, section))


def camera_config_from_widget(root: _Widget) -> Gphoto2CameraConfig:
    """Convert the root widget returned by camera.get_config() into plain data."""
    widgets: list[Gphoto2ConfigWidget] = []
    _collect(root, root.get_label() or "", widgets)

    by_name = {widget.name: widget for widget in widgets}

    mode = next((by_name[name] for name in EXPOSURE_MODE_NAMES if name in by_name), None)

    model = None
    for name in ("cameramodel", "model"):
        if name in by_name and by_name[name].value:
            model = by_name[name].value
            break

    return Gphoto2CameraConfig(model=model, mode=mode, widgets=widgets)
