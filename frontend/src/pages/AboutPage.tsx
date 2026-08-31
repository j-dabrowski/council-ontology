export function AboutPage() {
  return (
    <div className="static-page">
      <div className="static-hero">
        <h1 className="static-h1">Civic intelligence for local government</h1>
        <p className="static-lead">
          Local councils make the decisions that shape where you live — planning
          approvals, contract spending, conflict-of-interest management. Those
          decisions are buried in meeting minutes that almost no one reads.
          Intelcrier changes that.
        </p>
      </div>

      <section className="static-section">
        <h2 className="static-h2">What we do</h2>
        <p>
          We extract, structure, and analyse decades of council meeting minutes
          using large language models, then publish the results as an interactive
          dashboard built on a standard, comparable test battery. Every finding
          links to the verbatim source quote in the original minute. Every claim
          is anchored to a recognised governance standard.
        </p>
        <p>
          The same battery runs on every council we analyse — so you can compare
          Town of Cambridge against City of Fremantle against City of Perth on
          identical criteria. A green result means the data actively supports
          good practice. A critical result means a pattern the evidence warrants
          explaining. Nothing asserts wrongdoing.
        </p>
      </section>

      <section className="static-section">
        <h2 className="static-h2">The Standard Test Battery</h2>
        <p>
          Every council analysis runs the same 23 governance tests across five
          domains, each flagged{" "}
          <span className="valence-chip valence-supportive">supportive</span>,{" "}
          <span className="valence-chip valence-neutral">neutral</span>, or{" "}
          <span className="valence-chip valence-critical">critical</span> and
          anchored to a named principle:
        </p>
        <div className="about-domains">
          <div className="about-domain">
            <div className="about-domain-title">Integrity &amp; procurement</div>
            <div className="about-domain-desc">
              Conflict-of-interest disclosure and management, tender concentration,
              threshold-gaming, entrenched incumbents, repeat-applicant advantage
            </div>
          </div>
          <div className="about-domain">
            <div className="about-domain-title">Governance &amp; culture</div>
            <div className="about-domain-desc">
              Power distribution, unanimity, factional structure, tenure and
              entrenchment, officer vs chamber alignment, mayoral influence
            </div>
          </div>
          <div className="about-domain">
            <div className="about-domain-title">Transparency</div>
            <div className="about-domain-desc">
              Confidential business share over time — how open is the chamber
              about what it decides and why?
            </div>
          </div>
          <div className="about-domain">
            <div className="about-domain-title">Public engagement</div>
            <div className="about-domain-desc">
              Deputation and objection patterns, whether community input
              actually changes outcomes, who shows up and about what
            </div>
          </div>
          <div className="about-domain">
            <div className="about-domain-title">Financial</div>
            <div className="about-domain-desc">
              End-of-year spending patterns, reserve trajectory, single-source
              procurement — where the public record allows
            </div>
          </div>
        </div>
        <p>
          The battery is grounded in the{" "}
          <strong>Nolan Principles of Public Life</strong> (selflessness,
          integrity, objectivity, accountability, openness, honesty, leadership)
          and the <strong>CIPFA / SOLACE good governance framework</strong> for
          local authorities.
        </p>
      </section>

      <section className="static-section">
        <h2 className="static-h2">Balanced by design</h2>
        <p>
          Our methodology runs every finding through both a critic and a
          defender before publishing. Findings that survive a rigorous
          promoter challenge are labelled governance-concerns; results where
          the evidence clears the council are labelled strengths. A council
          that passes every test gets full credit. We do not amplify concerns
          by default.
        </p>
        <p>
          We also publish our null results — tests that found nothing notable.
          The absence of procurement corruption signatures is itself a finding:
          it means the council cleared three independent integrity tests.
        </p>
      </section>

      <section className="static-section">
        <h2 className="static-h2">The technology</h2>
        <p>
          Public meeting minutes (PDF) are scraped from council websites, then
          passed through a multi-level LLM extraction pipeline using{" "}
          <strong>Anthropic Claude</strong>. The pipeline extracts motions,
          votes, planning applications, tender awards, conflict declarations,
          deputations, and more into a structured SQLite database. The standard
          test battery then runs SQL-based analyses against that database and
          exports static JSON snapshots to the dashboard.
        </p>
        <p>
          Extraction quality is validated at multiple stages: quote completeness,
          paraphrase rate, and entity density checks. Every finding displayed in
          the dashboard links to a verbatim source quote from the original minute
          document.
        </p>
      </section>

      <section className="static-section">
        <h2 className="static-h2">Coverage</h2>
        <p>
          Currently live: <strong>Town of Cambridge, Western Australia</strong>{" "}
          (1995–2026 · 537 documents · 30-year corpus).
        </p>
        <p>
          Expanding across Western Australia and nationally. If you represent a
          council, a media organisation, a watchdog body, or a research group
          and want to talk about coverage priorities, get in touch.
        </p>
      </section>

      <section className="static-section">
        <h2 className="static-h2">Who we are</h2>
        <p>
          Intelcrier is a civic intelligence company based in Western Australia.
          Our mission is to make local government accountability visible at
          scale — not through advocacy, but through evidence.
        </p>
        <p>
          For enquiries, corrections, or media requests, see our{" "}
          <a href="#/contact">Contact</a> page.
        </p>
      </section>
    </div>
  );
}
