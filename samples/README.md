# Sample referral corpus

Six fabricated referral documents, one per intake channel in the **PHI
Sources** box of the reference architecture. They exist so an attendee can
drive the full upload -> dual-engine extraction -> comparison -> human
approval flow without any real referral data, and so extraction quality can
actually be measured instead of eyeballed.

| File | Channel | Format | Difficulty | What it exercises |
|---|---|---|---|---|
| `referral-portal-submission.pdf` | Referral Portals | PDF | easy | Clean digital text; the extraction baseline |
| `fax-referral-transmission.png` | Fax Systems | PNG, 200 dpi bitonal | hard | OCR through skew, speckle, and scanner streaks |
| `email-attachment-referral.pdf` | Email Attachments | PDF | easy | Separating transport headers from clinical content |
| `scanned-intake-form.png` | Scanned Patient Documents | PNG, 300 dpi | hard | Handwriting, a hand-drawn checkbox, a signature |
| `provider-referral-packet.pdf` | Provider Referral Packets | PDF, 4 pages | medium | Face sheet + H&P + med list + signed order in one file |
| `partner-network-referral.pdf` | External Healthcare Partners | PDF | medium | Dense HL7-style segment table layout |

Each referral is a **different patient with a different clinical story**, so
the comparison table shows meaningfully different output per document rather
than the same row six times.

## These are not real records

Every value is fabricated. Safety comes from using identifier ranges reserved
for fiction rather than from stamping a banner across the page, so the
documents stay representative of what a production system would actually
receive:

- Phone and fax numbers use the `555-01xx` block reserved for fictional use.
- Email domains use `example.com` / `example.org` (RFC 2606).
- NPIs are ten digits that deliberately **fail** the required Luhn check
  digit, so they cannot collide with a registered provider.
- MRNs, member IDs, and authorization numbers follow plausible formats but
  belong to organizations that do not exist.

## `manifest.json`

`manifest.json` is the ground truth for the corpus: for each document it
records the channel, the difficulty, the expected value of every extracted
field, and `reviewerMustConfirm` - the fields a human reviewer is *expected*
to have to correct.

Two documents deliberately carry ambiguity so the human-in-the-loop review
step has real work to do rather than rubber-stamping a perfect extraction.
That is the point of the review queue, and a corpus where every field
extracts perfectly would not demonstrate it.

Use the manifest to score a run:

```bash
az containerapp exec -n ca-referralintake-web-dev -g rg-referralintake \
  --command "python -m referral.diagnose --score"
```

## Uploading a sample by hand

Every file is a valid PDF/PNG matching its declared content type, which is
what `api/referral/guardrails.py` requires.

```bash
curl -X POST "https://<host>/api/referrals" \
  -F "document=@samples/referral-portal-submission.pdf;type=application/pdf"
```

```powershell
curl.exe -X POST "https://<host>/api/referrals" `
  -F "document=@samples/fax-referral-transmission.png;type=image/png"
```

The endpoint requires an authenticated caller per the deployed Easy Auth
configuration - see the [deployment instructions](../docs/deployment.md).

## Regenerating

```bash
python -m pip install reportlab pillow
python samples/generate_samples.py
```

Rendering is seeded, so regenerating produces byte-identical output unless
`scenarios.py` or a renderer changes. Ground truth lives in `scenarios.py`;
edit it there and the documents and `manifest.json` both follow.

The handwriting in `scanned-intake-form.png` uses
[Caveat](https://fonts.google.com/specimen/Caveat) under the SIL Open Font
License (`fonts/OFL.txt`).
