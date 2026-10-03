from __future__ import annotations

import json

import pytest

from scripts import probe_inline_pixel_presence as probe


class _Image:
    def __init__(self, pixels):
        self._pixels = pixels

    def getdata(self):
        return self._pixels


def test_screen_observer_requires_the_controlled_surface_color(monkeypatch):
    boxes = []

    def grab(*, bbox):
        boxes.append(bbox)
        return _Image([probe.BACKGROUND] * 55 + [(255, 0, 0)] * 9)

    monkeypatch.setattr(probe.ImageGrab, "grab", grab)
    assert probe._background_pixels(114, 118) == 55
    assert boxes == [(116, 120, 124, 128)]
    assert 55 < probe.PRESENCE_PIXELS


def test_missing_controlled_pixel_cannot_be_reported_as_a_pass():
    assert probe._verdict(2, 1, [{"reason": "pixel_not_observed"}]) == "fail"
    assert probe._verdict(2, 0, [{"reason": "background_ambiguous"}]) == "blocked"
    assert probe._verdict(2, 2, []) == "pass"


def test_denied_screen_capture_has_a_content_free_blocked_report(monkeypatch, tmp_path, capsys):
    def deny(*, bbox):
        raise OSError("screen grab failed")

    monkeypatch.setattr(probe.ImageGrab, "grab", deny)
    with pytest.raises(probe.ScreenCaptureUnavailable):
        probe._background_pixels(0, 0)

    def blocked_measure(*_args):
        raise probe.ScreenCaptureUnavailable

    monkeypatch.setattr(probe, "measure", blocked_measure)
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["probe", "--output", str(output)])
    assert probe.main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report == {
        "schema_version": 1,
        "scope": "controlled_inline_onscreen_pixel_presence",
        "status": "blocked",
        "reason": "screen_capture_unavailable",
        "observed_runs": 0,
        "pixel_data_saved": False,
    }
    assert "screen grab failed" not in capsys.readouterr().out
