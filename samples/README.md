# Synthetic sample referrals

This folder contains six entirely synthetic sample documents — one for each
intake channel ("PHI Sources") shown in the architecture diagram — so an
operator or workshop attendee can exercise the upload → AI extraction
comparison → human approval flow without needing any real referral data.

**None of these files contain real patient, provider, or organization
information.** Every document carries a "SYNTHETIC TEST DATA — NOT REAL PHI"
banner and only placeholder identifiers (patient "Pat Testerson", MRN
`SYN-000123`, DOB `2030-01-01`).

| File | PHI Sources channel | Format |
|---|---|---|
| `synthetic-referral-portal-submission.pdf` | Referral Portals | PDF |
| `synthetic-fax-referral-coversheet.png` | Fax Systems | PNG |
| `synthetic-email-attachment-referral.pdf` | Email Attachments | PDF |
| `synthetic-scanned-patient-chart.png` | Scanned Patient Documents | PNG |
| `synthetic-provider-referral-packet.pdf` | Provider Referral Packets | PDF (2 pages) |
| `synthetic-external-partner-referral.pdf` | External Healthcare Partners | PDF |

These are illustrative reference documents for exercising the pipeline, not a
representative corpus of every real-world referral layout, and the PNG
samples are stylized rather than scan/fax-artifact-realistic (no noise, skew,
or compression artifacts).

## Uploading a sample to the running API

The API enforces (`api/referral/guardrails.py`) that uploaded filenames begin
with `synthetic-`, declare `X-Data-Classification: synthetic`, and are a real
PDF/PNG/JPEG matching their declared content type — every file in this folder
already satisfies that.

```powershell
curl.exe -X POST "https://<function-or-aca-host>/api/referrals" `
  -H "X-Data-Classification: synthetic" `
  -F "document=@samples/synthetic-referral-portal-submission.pdf;type=application/pdf"
```

```bash
curl -X POST "https://<function-or-aca-host>/api/referrals" \
  -H "X-Data-Classification: synthetic" \
  -F "document=@samples/synthetic-fax-referral-coversheet.png;type=image/png"
```

Swap the `-F` value's file path/`type` for any of the six samples (use
`type=application/pdf` for the `.pdf` files and `type=image/png` for the
`.png` files). The endpoint requires the caller to already be authenticated
per the deployed Easy Auth configuration — see [deployment
instructions](../docs/deployment.md).

## Regenerating the samples

The samples are produced by `generate_samples.py` using
[`reportlab`](https://pypi.org/project/reportlab/) (PDFs) and
[`Pillow`](https://pypi.org/project/Pillow/) (PNGs):

```bash
python3 -m venv .venv
.venv/bin/pip install reportlab pillow
.venv/bin/python samples/generate_samples.py
```

This overwrites the six files in place with freshly generated versions.
