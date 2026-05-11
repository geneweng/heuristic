from cost import Usage


def test_opus_cost_matches_published_rates():
    u = Usage(model="claude-opus-4-7", input_tokens=1_000_000, output_tokens=0)
    assert u.cost_usd == 15.0

    u = Usage(model="claude-opus-4-7", input_tokens=0, output_tokens=1_000_000)
    assert u.cost_usd == 75.0


def test_haiku_is_cheaper_than_opus():
    o = Usage("claude-opus-4-7", 1000, 500)
    h = Usage("claude-haiku-4-5", 1000, 500)
    assert h.cost_usd < o.cost_usd


def test_unknown_model_costs_zero_but_records_tokens():
    u = Usage("imaginary-model", 1000, 500)
    assert u.cost_usd == 0.0
    assert u.as_dict()["input_tokens"] == 1000
