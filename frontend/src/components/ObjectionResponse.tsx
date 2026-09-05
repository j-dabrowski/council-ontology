import { ResolvedTest } from "../registry/types";

type ObjectionResponseProps =
  | { test: ResolvedTest }
  | { objection: string; response: string };

// Two fixed, identically-rendered labelled slots — "Objection" and
// "Response" — for the registry's number-free counter-argument text
// (PANEL_FRAMING_PLAN.md B.1). Either resolve the pair from a ResolvedTest,
// or (B.6, the one caller with no registry row) pass the two strings
// directly. Renders nothing when either half is missing.
export function ObjectionResponse(props: ObjectionResponseProps) {
  const objection = "test" in props ? props.test.objection : props.objection;
  const response = "test" in props ? props.test.response : props.response;

  if (!objection || !response) {
    if ("test" in props && props.test.valence === "critical") {
      console.error(
        `ObjectionResponse: critical-valence test "${props.test.id}" has no objection/response pair — skipped`
      );
    }
    return null;
  }

  return (
    <div className="objection-response">
      <div className="objection-response-row">
        <span className="objection-response-label">Objection</span>
        <p className="objection-response-text">{objection}</p>
      </div>
      <div className="objection-response-row">
        <span className="objection-response-label">Response</span>
        <p className="objection-response-text">{response}</p>
      </div>
    </div>
  );
}
