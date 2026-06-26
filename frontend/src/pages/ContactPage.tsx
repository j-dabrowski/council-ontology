export function ContactPage() {
  return (
    <div className="static-page">
      <div className="static-hero">
        <h1 className="static-h1">Get in touch</h1>
        <p className="static-lead">
          We take data accuracy seriously. If you believe something we've
          published is incorrect, please tell us — we will investigate and
          correct within five business days.
        </p>
      </div>

      <div className="contact-grid">
        <div className="contact-card">
          <div className="contact-card-icon">✉</div>
          <h2 className="contact-card-title">General enquiries</h2>
          <p className="contact-card-desc">
            Business development, partnerships, coverage requests, media,
            or anything else.
          </p>
          <a className="contact-card-link" href="mailto:hello@intelcrier.com">
            hello@intelcrier.com
          </a>
        </div>

        <div className="contact-card">
          <div className="contact-card-icon">⚑</div>
          <h2 className="contact-card-title">Corrections</h2>
          <p className="contact-card-desc">
            If you believe a finding, statistic, or attribution on this site
            is factually incorrect, please write to us with the specific claim
            and supporting evidence.
          </p>
          <a className="contact-card-link" href="mailto:corrections@intelcrier.com">
            corrections@intelcrier.com
          </a>
        </div>

        <div className="contact-card">
          <div className="contact-card-icon">◎</div>
          <h2 className="contact-card-title">Research &amp; data</h2>
          <p className="contact-card-desc">
            Academic or policy research enquiries, data licensing, or requests
            for custom analysis.
          </p>
          <a className="contact-card-link" href="mailto:research@intelcrier.com">
            research@intelcrier.com
          </a>
        </div>
      </div>

      <section className="static-section">
        <h2 className="static-h2">Our corrections process</h2>
        <p>
          Everything published on this site is sourced from publicly available
          council meeting minutes. Each data point links to a verbatim quote
          from the source document — you can verify any claim by clicking the
          source toggle in the relevant panel.
        </p>
        <p>
          If you contact us with a correction, we will:
        </p>
        <ol className="contact-list">
          <li>Acknowledge receipt within one business day</li>
          <li>
            Investigate the specific claim against the source documents and
            our extraction database
          </li>
          <li>
            Correct and republish within five business days if the claim is
            found to be inaccurate, or explain our methodology if we maintain
            the finding
          </li>
          <li>
            Note the correction in our records
          </li>
        </ol>
        <p>
          We are particularly interested in corrections from councillors or
          council officers who have direct knowledge of the matters discussed.
          Your perspective on the context behind a finding is valuable even
          if the underlying data is accurate.
        </p>
      </section>

      <section className="static-section">
        <h2 className="static-h2">About the data</h2>
        <p>
          All analysis is based on information extracted from{" "}
          <strong>publicly available council meeting minutes</strong> and
          published official records. Findings relate to official conduct in
          official capacities and are grounded in recognised governance
          standards (Nolan Principles; CIPFA / SOLACE framework).
        </p>
        <p>
          Findings are published at <em>Observation</em> or{" "}
          <em>Governance-concern</em> altitude — they describe patterns
          that warrant explanation against a named principle. Nothing on
          this site asserts wrongdoing or intent.
        </p>
        <p>
          For a full description of our methodology, see the{" "}
          <a href="#/about">About</a> page.
        </p>
      </section>
    </div>
  );
}
