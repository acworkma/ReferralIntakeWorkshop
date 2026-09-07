import { STAGES, stageState } from "../pipeline";

interface Props {
  /** Index into STAGES of the step the document has actually reached. */
  current: number;
  /** The container the API reports the document is in right now. */
  container: string | null;
  failed?: boolean;
}

/**
 * The document's position in the pipeline, drawn from the container it is
 * physically in. This is the point of the whole architecture: the container is
 * the state, so the trail shows the real container name rather than a label
 * invented by the UI.
 */
export function PipelineTrail({ current, container, failed = false }: Props) {
  const stage = STAGES[current];
  return (
    <div className="trail-block">
      <ol className="trail">
        {STAGES.map((step, index) => {
          const state = stageState(index, current);
          const isCurrent = state === "current";
          return (
            <li
              key={step.key}
              className={`trail-step ${state}${isCurrent && failed ? " failed" : ""}`}
              aria-current={isCurrent ? "step" : undefined}
            >
              <span className="trail-dot" aria-hidden="true" />
              <span className="trail-copy">
                <strong>{step.label}</strong>
                <small>{isCurrent && container ? container : step.container}</small>
              </span>
            </li>
          );
        })}
      </ol>
      <p className="trail-detail">{stage.detail}</p>
    </div>
  );
}
