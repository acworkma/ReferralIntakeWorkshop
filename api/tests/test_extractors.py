from referral.extractors import _compose_summary, _values_agree, compare
from referral.schema import COMPARABLE_FIELDS, FIELDS, QUERY_FIELDS, analyzer_field_schema


def test_composed_summary_reads_as_prose_not_raw_text():
    summary = _compose_summary(
        {
            "patientName": "Marcus Oyelaran",
            "requestedService": "Physical therapy",
            "primaryDiagnosis": "Status post right total knee arthroplasty",
            "diagnosisCode": "Z96.651",
            "priority": "Routine",
            "requestedDate": "2030-03-11",
            "referringProvider": "Helen Zhao, MD",
        }
    )
    assert summary.startswith("Marcus Oyelaran was referred for physical therapy.")
    assert "Z96.651" in summary
    assert "2030-03-11" in summary


def test_composed_summary_skips_missing_fields():
    # "Not found" must never leak into the prose, and a document with nothing
    # usable reports that plainly instead of inventing a sentence.
    summary = _compose_summary({"patientName": "Rowan Alvarez", "priority": "Not found"})
    assert "Not found" not in summary
    assert _compose_summary({"patientName": "Not found"}) == "Not found"


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
