from pose_care.notifications import WindowsNotifier


class FakeToaster:
    def __init__(self):
        self.sent = []

    def show_toast(self, toast):
        self.sent.append(toast)


def test_native_notification_is_built_and_sent():
    toaster = FakeToaster()
    notifier = WindowsNotifier(toaster=toaster, toast_factory=lambda fields: tuple(fields))
    assert notifier.send("Title", "Body")
    assert toaster.sent == [("Title", "Body")]


def test_native_notification_failure_returns_false():
    class BrokenToaster:
        def show_toast(self, toast):
            raise RuntimeError("failed")

    notifier = WindowsNotifier(toaster=BrokenToaster(), toast_factory=lambda fields: fields)
    assert not notifier.send("Title", "Body")
    assert notifier.last_error == "failed"


def test_native_notification_runs_activation_callback_when_clicked():
    class FakeToast:
        def __init__(self, fields):
            self.fields = fields
            self.on_activated = None

    toaster = FakeToaster()
    notifier = WindowsNotifier(toaster=toaster, toast_factory=FakeToast)
    activations = []

    assert notifier.send(
        "Title",
        "Body",
        lambda: activations.append("opened"),
    )
    toaster.sent[0].on_activated(object())

    assert activations == ["opened"]
