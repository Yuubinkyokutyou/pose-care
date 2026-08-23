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
