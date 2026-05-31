from collections.abc import Sequence

from lazyworker.interaction.ocr import recognize


def _engine(_path: str) -> list[tuple[str, float, Sequence[float]]]:
    # (text, confidence, normalized bottom-left box [x, y, w, h])
    return [
        ("Saldo", 1.0, [0.0757, 0.779, 0.082, 0.013]),
        ("R$ 1.234,56", 0.98, [0.0787, 0.728, 0.372, 0.035]),
    ]


def test_recognize_converts_normalized_to_points() -> None:
    texts = recognize("/x.png", screen_width=402, screen_height=874, engine=_engine)
    saldo = next(t for t in texts if t.text == "Saldo")
    # x = 0.0757*402 ~= 30 ; y = (1 - 0.779 - 0.013)*874 ~= 182 (bottom-left -> top-left)
    assert saldo.box[0] == 30
    assert saldo.box[1] == 182
    assert saldo.size == (saldo.box[2], saldo.box[3])
    assert saldo.confidence == 1.0


def test_recognize_sorts_reading_order() -> None:
    texts = recognize("/x.png", screen_width=402, screen_height=874, engine=_engine)
    tops = [t.box[1] for t in texts]
    assert tops == sorted(tops)


def test_recognize_rounds_confidence() -> None:
    def engine(_path: str) -> list[tuple[str, float, Sequence[float]]]:
        return [("x", 0.987654, [0.1, 0.1, 0.1, 0.1])]

    text = recognize("/x.png", screen_width=100, screen_height=100, engine=engine)[0]
    assert text.confidence == 0.988
