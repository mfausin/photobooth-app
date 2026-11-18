from photobooth.services.backends.gphoto2_config import camera_config_from_widget


class FakeWidget:
    """Minimal stand-in for gphoto2's CameraWidget."""

    def __init__(self, name, label, typ, value=None, choices=(), readonly=0, children=(), range_=None, fail_value=False):
        self._name, self._label, self._typ = name, label, typ
        self._value, self._choices, self._readonly = value, list(choices), readonly
        self._children, self._range, self._fail_value = list(children), range_, fail_value

    def get_name(self):
        return self._name

    def get_label(self):
        return self._label

    def get_type(self):
        return self._typ

    def get_readonly(self):
        return self._readonly

    def get_value(self):
        if self._fail_value:
            raise RuntimeError("driver error")
        return self._value

    def get_choices(self):
        return iter(self._choices)

    def get_range(self):
        return self._range

    def count_children(self):
        return len(self._children)

    def get_child(self, index):
        return self._children[index]


WINDOW, SECTION, TEXT, RANGE, TOGGLE, RADIO, MENU, BUTTON, DATE = range(9)


def canon_like_tree():
    return FakeWidget(
        "main",
        "Camera and Driver Configuration",
        WINDOW,
        children=[
            FakeWidget(
                "status",
                "Camera Status Information",
                SECTION,
                children=[
                    FakeWidget("cameramodel", "Camera Model", TEXT, "Canon EOS 2000D", readonly=1),
                    FakeWidget("batterylevel", "Battery Level", TEXT, "100%", readonly=1),
                ],
            ),
            FakeWidget(
                "settings",
                "Camera Settings",
                SECTION,
                children=[
                    FakeWidget("viewfinder", "Canon EOS Viewfinder", TOGGLE, 0),
                    FakeWidget("datetime", "Camera Date and Time", DATE, 1700000000),
                    FakeWidget("capturetarget", "Capture Target", RADIO, "Memory card", ["Internal RAM", "Memory card"]),
                ],
            ),
            FakeWidget(
                "capturesettings",
                "Capture Settings",
                SECTION,
                children=[
                    FakeWidget("autoexposuremode", "Canon Auto Exposure Mode", RADIO, "Manual", ["P", "TV", "AV", "Manual"], readonly=1),
                    FakeWidget("iso", "ISO Speed", RADIO, "Auto", ["Auto", "100", "200", "400"]),
                    FakeWidget("shutterspeed", "Shutter Speed", RADIO, "1/60", ["bulb", "1/60", "1/125"]),
                    FakeWidget("zoom", "Zoom", RANGE, 3.0, range_=(0.0, 10.0, 1.0)),
                    FakeWidget("broken", "Broken", TEXT, fail_value=True),
                ],
            ),
            FakeWidget("actions", "Camera Actions", SECTION, children=[FakeWidget("autofocusdrive", "Drive Canon DSLR Autofocus", TOGGLE, 0)]),
            FakeWidget("trigger", "Trigger", BUTTON),
        ],
    )


def test_camera_config_flattens_sections_and_reads_model_and_mode():
    config = camera_config_from_widget(canon_like_tree())

    assert config.model == "Canon EOS 2000D"
    assert config.mode is not None
    assert config.mode.name == "autoexposuremode"
    assert config.mode.value == "Manual"
    assert config.mode.choices == ["P", "TV", "AV", "Manual"]

    by_name = {w.name: w for w in config.widgets}
    assert by_name["iso"].section == "Capture Settings"
    assert by_name["iso"].choices == ["Auto", "100", "200", "400"]
    assert by_name["iso"].settable
    assert by_name["viewfinder"].type == "toggle"
    assert by_name["viewfinder"].value == "0"
    assert by_name["viewfinder"].settable


def test_camera_config_marks_unsupported_and_readonly_as_not_settable():
    by_name = {w.name: w for w in camera_config_from_widget(canon_like_tree()).widgets}

    assert not by_name["cameramodel"].settable  # readonly
    assert not by_name["autoexposuremode"].settable  # readonly mode dial
    assert not by_name["datetime"].settable  # date not supported by the backend
    assert not by_name["trigger"].settable  # button
    assert not by_name["zoom"].settable  # range not supported by the backend
    assert (by_name["zoom"].range_min, by_name["zoom"].range_max, by_name["zoom"].range_step) == (0.0, 10.0, 1.0)
    assert by_name["zoom"].value == "3"


def test_camera_config_keeps_widgets_whose_value_fails():
    by_name = {w.name: w for w in camera_config_from_widget(canon_like_tree()).widgets}

    assert by_name["broken"].value == ""


def test_camera_config_mode_priority_and_missing_mode():
    tree = FakeWidget(
        "main",
        "Main",
        WINDOW,
        children=[
            FakeWidget("expprogram", "Exposure Program", RADIO, "M", ["P", "A", "S", "M"]),
            FakeWidget("autoexposuremodedial", "Canon Auto Exposure Mode Dial", RADIO, "AV", ["P", "AV"]),
        ],
    )
    assert camera_config_from_widget(tree).mode.name == "autoexposuremodedial"  # pyrefly: ignore [missing-attribute]

    no_mode = FakeWidget("main", "Main", WINDOW, children=[FakeWidget("iso", "ISO", RADIO, "100", ["100"])])
    config = camera_config_from_widget(no_mode)
    assert config.mode is None
    assert config.model is None


def test_camera_mode_mismatch():
    from photobooth.services.backends.gphoto2_config import camera_mode_mismatch

    config = camera_config_from_widget(canon_like_tree())  # autoexposuremode=Manual

    assert camera_mode_mismatch("", config) is None
    assert camera_mode_mismatch("autoexposuremode=Manual", config) is None
    assert "autoexposuremode=AV" in (camera_mode_mismatch("autoexposuremode=AV", config) or "")
    assert "does not report 'expprogram'" in (camera_mode_mismatch("expprogram=M", config) or "")
