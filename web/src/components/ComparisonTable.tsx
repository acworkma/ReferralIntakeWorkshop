import { fieldLabel } from "../pipeline";
import type { ComparisonRow } from "../types";

// An engine that returns no score for a field is not the same as an engine that
// is certain the field is wrong. Rendering a bare "0% confidence" conflated the
// two and made sound extractions look worthless.
function Confidence({ value }: { value: number }) {
  if (!value) return null;
  return <small>{Math.round(value * 100)}%</small>;
}

interface Props {
  rows: ComparisonRow[];
  agreementPercent: number;
}

export function ComparisonTable({ rows, agreementPercent }: Props) {
  const disagreements = rows.filter((row) => !row.matches).length;
  return (
    <section className="panel">
      <header className="panel-head">
        <h3>Extraction evidence</h3>
        <span className="agreement-chip">
          <strong>{agreementPercent}%</strong> field agreement
        </span>
      </header>
      <p className="panel-note">
        {disagreements === 0
          ? "Both engines read every comparable field the same way. Confirm the values still match the document before approving."
          : `${disagreements} ${disagreements === 1 ? "field is" : "fields are"} read differently by the two engines. That is independent of confidence: an engine can be certain and still be wrong, which is what a reviewer is here to catch.`}
      </p>
      <table className="comparison">
        <thead>
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Document Intelligence</th>
            <th scope="col">Content Understanding</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field} className={row.matches ? "" : "diff"}>
              <th scope="row">
                {fieldLabel(row.field)}
                {!row.matches && <em className="row-flag">engines disagree</em>}
                {row.comparable === false && (
                  <em className="row-note">generated prose, not compared</em>
                )}
              </th>
              <td>
                <span>{row.documentIntelligence}</span>
                <Confidence value={row.documentIntelligenceConfidence} />
              </td>
              <td>
                <span>{row.contentUnderstanding}</span>
                <Confidence value={row.contentUnderstandingConfidence} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
