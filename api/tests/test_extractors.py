from referral.extractors import _values_agree, compare
from referral.schema import COMPARABLE_FIELDS, FIELDS, QUERY_FIELDS, analyzer_field_schema


def test_comparison_has_traceable_fields():
    content = b"%PDF demo referral"
    result = compare(content, "a" * 64)
    assert [row["field"] for row in result["rows"]] == list(FIELDS)
    assert 0 <= result["agreementPercent"] <= 100
    assert all("matches" in row for row in result["rows"])


def test_generated_summary_is_excluded_from_agreement():
    # The engines word prose differently, so scoring it would make the
    # agreement number meaningless.
    assert "summary" in FIELDS
    assert "summary" not in COMPARABLE_FIELDS


def test_query_fields_fit_document_intelligence_limit():
    assert len(QUERY_FIELDS) <= 20
    assert "summary" not in QUERY_FIELDS


def test_value_comparison_ignores_formatting_noise():
    assert _values_agree("Rowan Alvarez", "  rowan   alvarez ")
    assert _values_agree("Raman, Priya", "Raman Priya")
    assert not _values_agree("Routine", "Urgent")


def test_analyzer_schema_marks_priority_as_a_classification():
    fields = analyzer_field_schema()["fields"]
    assert set(fields) == set(FIELDS)
    assert fields["priority"]["method"] == "classify"
    assert fields["priority"]["enum"] == ["Routine", "Urgent", "STAT"]
    assert fields["summary"]["method"] == "generate"
    assert fields["patientDateOfBirth"]["type"] == "date"
