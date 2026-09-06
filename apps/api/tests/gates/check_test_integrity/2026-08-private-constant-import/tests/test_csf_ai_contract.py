from app.csf.playbook import _PARSER_ROW_KEYS


def test_prompt_compliant_response_parses():
    response = {k: 1 for k in _PARSER_ROW_KEYS}
    assert set(response) == set(_PARSER_ROW_KEYS)
