from lazyworker.interaction.detect import DetectedElement
from lazyworker.interaction.screen import describe_screen
from lazyworker.wda.models import AccessibilityNode


def _tree() -> AccessibilityNode:
    return AccessibilityNode.model_validate(
        {
            "type": "Application",
            "rect": {"x": 0, "y": 0, "width": 402, "height": 874},
            "isVisible": True,
            "children": [
                {
                    "type": "Window",
                    "rect": {"x": 0, "y": 0, "width": 402, "height": 874},
                    "isVisible": True,
                    "children": [
                        {
                            "type": "Cell",
                            "rawIdentifier": "card-1",
                            "rect": {"x": 16, "y": 120, "width": 370, "height": 96},
                            "isVisible": True,
                            "children": [
                                {
                                    "type": "StaticText",
                                    "label": "Saldo",
                                    "rect": {"x": 32, "y": 132, "width": 80, "height": 20},
                                    "isVisible": True,
                                    "children": [],
                                },
                                {
                                    "type": "StaticText",
                                    "label": "R$ 1.234,56",
                                    "rect": {"x": 32, "y": 156, "width": 160, "height": 28},
                                    "isVisible": True,
                                    "children": [],
                                },
                            ],
                        },
                        {
                            "type": "Button",
                            "label": "Pay",
                            "rawIdentifier": "btn-pay",
                            "rect": {"x": 16, "y": 230, "width": 370, "height": 44},
                            "isVisible": True,
                            "children": [],
                        },
                    ],
                }
            ],
        }
    )


def test_describe_screen_size_and_meta() -> None:
    description = describe_screen(_tree(), screenshot="/x.png", bundle_id="com.x")
    assert description.width == 402
    assert description.height == 874
    assert description.screenshot == "/x.png"
    assert description.bundle_id == "com.x"


def test_excludes_structural_roles() -> None:
    description = describe_screen(_tree(), screenshot="/x.png")
    assert not any(e.role in ("Application", "Window") for e in description.elements)


def test_card_and_grouped_texts() -> None:
    description = describe_screen(_tree(), screenshot="/x.png")
    card = next(e for e in description.elements if e.identifier == "card-1")
    assert card.interactive
    assert card.box == (16, 120, 370, 96)
    assert card.size == (370, 96)

    saldo = next(e for e in description.elements if e.text == "Saldo")
    assert saldo.container == "card-1"
    assert saldo.box == (32, 132, 80, 20)


def test_reading_order_top_to_bottom() -> None:
    description = describe_screen(_tree(), screenshot="/x.png")
    tops = [e.box[1] for e in description.elements]
    assert tops == sorted(tops)


def test_detection_container_assignment() -> None:
    detection = DetectedElement(label="icon", box=(200, 140, 20, 20), size=(20, 20), confidence=0.9)
    description = describe_screen(_tree(), screenshot="/x.png", detections=[detection])
    assert description.detections is not None
    # center (210, 150) is inside the card frame [16,120,370,96]
    assert description.detections[0].container == "card-1"


def test_button_is_interactive_with_text() -> None:
    description = describe_screen(_tree(), screenshot="/x.png")
    pay = next(e for e in description.elements if e.identifier == "btn-pay")
    assert pay.interactive
    assert pay.text == "Pay"
