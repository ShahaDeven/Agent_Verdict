import pytest

from agent_verdict.web_agent import _readable, parse_action


def test_multiline_text_inside_json_is_accepted():
    # Ember often writes a multi-line customer reply; strict JSON parsing rejected these (Nov 27 live run)
    raw = '{"thought":"reply","action":"fill","element":6,"text":"Hi Ana,\nYou can request a refund within 30 days."}'
    assert parse_action(raw) == ("fill", 6, "Hi Ana,\nYou can request a refund within 30 days.", "reply")


def test_code_fences_and_string_element():
    assert parse_action('```json\n{"thought":"t","action":"click","element":"5","text":""}\n```') == ("click", 5, "", "t")


@pytest.mark.parametrize("raw", ["", "I will click the button.", '{"action":"teleport","element":1,"text":"","thought":""}'])
def test_unusable_answers_raise(raw):
    with pytest.raises(ValueError):
        parse_action(raw)


def test_readable_actions_use_labels():
    assert _readable("click", "Place order", "") == "click('Place order')"
    assert _readable("send_msg_to_user", "", "It's done") == "send_msg_to_user('It’s done')"
