import { CouncilHeader } from "../components/CouncilHeader";

export function EvidencePage() {
  return (
    <div className="app">
      <CouncilHeader />

      <div className="evidence-prose">
        <div className="static-hero">
          <h2 className="static-h1">Evidence</h2>
          <p className="static-lead">
            Every finding in this report is grounded in the public record —
            verbatim quotes from meeting minutes, agenda items, and council documents
            spanning 1995 to 2026.
          </p>
        </div>

        <div className="static-section">
          <h3 className="static-h2">How to find source evidence now</h3>
          <p>
            Each panel in the <a href="#/analysis">Full Analysis</a> links directly to
            its source material. Look for the "Show source" toggle beneath individual
            findings — it expands the verbatim quote from the original minutes.
          </p>
          <p>
            Councillor profiles (click any name in the report) also surface their
            voting history, declared interests, and committee roles with direct
            references to the relevant meeting.
          </p>
        </div>

        <div className="static-section">
          <h3 className="static-h2">Planned for this section</h3>
          <div className="about-domains">
            <div className="about-domain">
              <div className="about-domain-title">Source document browser</div>
              <div className="about-domain-desc">
                Navigate the full corpus of meeting minutes by date, agenda item,
                or councillor — with quotes in context.
              </div>
            </div>
            <div className="about-domain">
              <div className="about-domain-title">Raw data export</div>
              <div className="about-domain-desc">
                Download structured datasets — votes, tenders, declarations, motions —
                for independent analysis.
              </div>
            </div>
            <div className="about-domain">
              <div className="about-domain-title">Methodology notes</div>
              <div className="about-domain-desc">
                Detailed write-ups for each test: what was measured, how extraction
                was validated, and known limitations.
              </div>
            </div>
            <div className="about-domain">
              <div className="about-domain-title">Audit trail</div>
              <div className="about-domain-desc">
                Full provenance for every data point: which source document, which
                extraction run, and any manual corrections applied.
              </div>
            </div>
          </div>
        </div>

        <div className="static-section">
          <h3 className="static-h2">Primary source</h3>
          <p>
            All data is derived from publicly available City of Cambridge council
            meeting minutes, published at{" "}
            <a
              href="https://www.cambridge.wa.gov.au/council/council-meetings"
              target="_blank"
              rel="noopener noreferrer"
            >
              cambridge.wa.gov.au
            </a>
            . Minutes from 2021 onward are available via the council's current CMS;
            earlier records (1995–2020) were sourced from archived documents.
          </p>
        </div>
      </div>

      <footer className="site-footer">
        <p>
          Source: City of Cambridge council meeting minutes (public record) ·
          Data extracted via Anthropic Claude ·{" "}
          <a
            href="https://www.cambridge.wa.gov.au/council/council-meetings"
            target="_blank"
            rel="noopener noreferrer"
          >
            cambridge.wa.gov.au
          </a>
        </p>
      </footer>
    </div>
  );
}
