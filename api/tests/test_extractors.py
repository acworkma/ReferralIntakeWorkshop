from referral.extractors import compare


def test_comparison_has_traceable_fields():
    content = b"%PDF demo referral"
    result = compare(content, "a" * 64)
    assert len(result["rows"]) == 5
    assert 0 <= result["agreementPercent"] <= 100
    assert all("matches" in row for row in result["rows"])
