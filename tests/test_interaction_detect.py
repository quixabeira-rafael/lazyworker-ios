from collections.abc import Sequence

from lazyworker.interaction.detect import detect


def _engine(_path: str) -> list[tuple[str, float, Sequence[float]]]:
    # (label, confidence, normalized top-left box [x, y, w, h])
    return [
        ("a back arrow", 0.9, [0.05, 0.06, 0.07, 0.06]),
        ("low conf noise", 0.1, [0.5, 0.5, 0.1, 0.1]),
    ]


def test_detect_converts_points_and_filters_low_confidence() -> None:
    elements = detect("/x.png", screen_width=400, screen_height=800, engine=_engine)
    assert len(elements) == 1  # low-confidence one dropped (default 0.3)
    element = elements[0]
    assert element.label == "a back arrow"
    assert element.box == (20, 48, 28, 48)
    assert element.size == (28, 48)
    assert element.confidence == 0.9


def test_detect_min_confidence_override() -> None:
    elements = detect(
        "/x.png", screen_width=400, screen_height=800, min_confidence=0.05, engine=_engine
    )
    assert len(elements) == 2


def test_detect_sorts_reading_order() -> None:
    def engine(_path: str) -> list[tuple[str, float, Sequence[float]]]:
        return [("b", 0.9, [0.1, 0.5, 0.1, 0.1]), ("a", 0.9, [0.1, 0.1, 0.1, 0.1])]

    elements = detect("/x.png", screen_width=100, screen_height=100, engine=engine)
    assert [e.label for e in elements] == ["a", "b"]
