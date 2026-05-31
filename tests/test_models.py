from lazyworker.wda.models import AccessibilityNode, Rect, Status

SAMPLE_TREE = {
    "type": "Application",
    "label": "Demo",
    "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
    "isEnabled": True,
    "isVisible": "1",
    "children": [
        {
            "type": "Button",
            "label": "Login",
            "rawIdentifier": "login_button",
            "rect": {"x": 100, "y": 200, "width": 100, "height": 40},
            "isEnabled": "true",
            "isVisible": True,
            "children": [],
        },
        {
            "type": "StaticText",
            "label": "Hidden",
            "isVisible": "0",
            "children": [],
        },
    ],
}


def test_rect_center() -> None:
    rect = Rect(x=100, y=200, width=100, height=40)
    assert rect.center == (150, 220)


def test_status_flattens_os() -> None:
    status = Status.model_validate(
        {"ready": True, "message": "ok", "os": {"name": "iOS", "version": "17.4"}}
    )
    assert status.ready is True
    assert status.os_name == "iOS"
    assert status.os_version == "17.4"


def test_node_bool_coercion() -> None:
    node = AccessibilityNode.model_validate(SAMPLE_TREE)
    assert node.enabled is True
    assert node.visible is True
    hidden = node.children[1]
    assert hidden.visible is False


def test_node_alias_mapping() -> None:
    node = AccessibilityNode.model_validate(SAMPLE_TREE)
    button = node.children[0]
    assert button.identifier == "login_button"


def test_walk_yields_all_nodes() -> None:
    node = AccessibilityNode.model_validate(SAMPLE_TREE)
    types = [n.type for n in node.walk()]
    assert types == ["Application", "Button", "StaticText"]


def test_find_by_identifier() -> None:
    node = AccessibilityNode.model_validate(SAMPLE_TREE)
    found = node.find(identifier="login_button")
    assert found is not None
    assert found.label == "Login"
    assert found.rect is not None
    assert found.rect.center == (150, 220)


def test_find_all_filters_by_visibility() -> None:
    node = AccessibilityNode.model_validate(SAMPLE_TREE)
    visible_texts = node.find_all(type="StaticText", visible=True)
    assert visible_texts == []
