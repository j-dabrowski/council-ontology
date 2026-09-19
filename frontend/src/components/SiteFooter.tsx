import { useParams } from "react-router-dom";
import { useCouncilList } from "../councils";

// Shared by every council-scoped page (OverviewPage, AnalysisPage, WatchPage,
// MethodPage) — each used to duplicate this footer with the council's full
// name and its source URL hardcoded twice (display text and href). Reads
// both from the active council's own councils.json entry instead (SECOND_
// COUNCIL_PLAN.md Phase 3.2/B7).
export function SiteFooter() {
  const { council } = useParams<{ council: string }>();
  const { list } = useCouncilList();
  const entry = list.find((c) => c.key === council);
  const displayName = entry?.display_name ?? council ?? "this council";
  const sourceUrl = entry?.source_url ?? null;
  const state = entry?.state ?? null;

  return (
    <footer className="site-footer">
      <p>
        Source: {displayName}{state && `, ${state}`} council meeting minutes (public record) ·
        Data extracted via Anthropic Claude
        {sourceUrl && (
          <>
            {" "}·{" "}
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
              {sourceUrl.replace(/^https?:\/\//, "")}
            </a>
          </>
        )}
      </p>
    </footer>
  );
}
