import { ResolvedTest } from "../registry/types";

// S9 right of reply (docs/uplift/migration/01-known-defects.md G-34):
// "sent to the Town on [date]; response here" on every claim a packet has
// gone out for. `test.reply` is null until council reply-packets has
// actually sent one for this claim — every current battery test is
// institutional (no named individual), so this renders nothing on a
// healthy run today. Built now, against the real TestReply shape, so a
// future named-individual claim gets this for free rather than waiting on
// a second build once one exists.
export function ReplyStatus({ test }: { test: ResolvedTest }) {
  const reply = test.reply;
  if (!reply) return null;

  const sentDate = new Date(reply.sent_at).toLocaleDateString("en-AU", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className="objection-response reply-status">
      <div className="objection-response-row">
        <span className="objection-response-label">Right of reply</span>
        <p className="objection-response-text">
          Sent to the council on {sentDate}.
          {reply.response
            ? " Response:"
            : reply.declined
              ? " The council declined to respond."
              : " No response received."}
        </p>
      </div>
      {reply.response && (
        <div className="objection-response-row">
          <span className="objection-response-label">The council's response</span>
          <p className="objection-response-text">{reply.response}</p>
        </div>
      )}
    </div>
  );
}
