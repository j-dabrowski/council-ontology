import { useData } from "../hooks/useData";
import { api, AlignmentPair } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

function rateColor(rate: number) {
  // 100% = deep green, 95% = mid green, <90% = yellow
  if (rate >= 0.999) return "#16a34a";
  if (rate >= 0.97) return "#22c55e";
  if (rate >= 0.95) return "#4ade80";
  if (rate >= 0.90) return "#86efac";
  return "#fde68a";
}

function textColor(rate: number) {
  return rate >= 0.95 ? "#fff" : "#1e293b";
}

export function AlignmentHeatmap() {
  const { data, loading, error } = useData(() => api.alignment());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const pairs = data.pairs;

  // Collect unique names preserving order by first appearance
  const nameSet = new Set<string>();
  pairs.forEach((p) => { nameSet.add(p.name_a); nameSet.add(p.name_b); });
  const names = [...nameSet];

  // 100% pairs, computed from data.pairs at render time — never hardcoded.
  // Same reasoning as SponsorshipNetworkPanel's topAlliances and PowerPanel's
  // mostProlific/mostEffective: the chart-note must hold for any dataset this
  // loads, not just whatever was true when the sentence was written.
  const pairs100 = [...pairs]
    .filter((p) => p.agreement_rate >= 0.999)
    .sort((a, b) => b.shared_votes - a.shared_votes);

  // Build map for fast lookup
  const pairMap = new Map<string, AlignmentPair>();
  pairs.forEach((p) => {
    pairMap.set(`${p.name_a}|${p.name_b}`, p);
    pairMap.set(`${p.name_b}|${p.name_a}`, p);
  });

  return (
    <Card title="Voting Alignment Heatmap" subtitle="Agreement rate on shared votes, 1995–2026" valence="neutral">
      <div className="heatmap-scroll">
        <table className="heatmap-table">
          <thead>
            <tr>
              <th></th>
              {names.map((n) => (
                <th key={n} className="heatmap-col-label" title={n}>
                  {n.split(" ").slice(-1)[0]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((rowName) => (
              <tr key={rowName}>
                <td className="heatmap-row-label">{rowName.split(" ").slice(-1)[0]}</td>
                {names.map((colName) => {
                  if (rowName === colName) {
                    return <td key={colName} className="heatmap-self" />;
                  }
                  const pair = pairMap.get(`${rowName}|${colName}`);
                  if (!pair) return <td key={colName} className="heatmap-empty" />;
                  const bg = rateColor(pair.agreement_rate);
                  const fg = textColor(pair.agreement_rate);
                  return (
                    <td
                      key={colName}
                      style={{ background: bg, color: fg }}
                      className="heatmap-cell"
                      title={`${rowName} ↔ ${colName}: ${(pair.agreement_rate * 100).toFixed(1)}% (${pair.shared_votes} votes)`}
                    >
                      {(pair.agreement_rate * 100).toFixed(0)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="chart-note">
        {pairs100.length > 0 && (
          <>
            100% pairs ({pairs100.length}): {pairs100.map((p, i) => (
              <span key={`${p.name_a}|${p.name_b}`}>
                {i > 0 && ", "}
                {p.name_a}/{p.name_b} (n={p.shared_votes})
              </span>
            ))} — tightest sub-blocs in an already near-unanimous chamber.{" "}
          </>
        )}
        Hover cells for shared vote count.
      </p>
    </Card>
  );
}
