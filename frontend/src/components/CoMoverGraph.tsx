import ForceGraph2D from "react-force-graph-2d";
import { useRef, useEffect, useState, useCallback } from "react";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

export function CoMoverGraph() {
  const { data, loading, error } = useData(() => api.coMovers());
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  const [graphWidth, setGraphWidth] = useState(600);

  const handleEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(400, 32);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setGraphWidth(el.offsetWidth);
    const ro = new ResizeObserver(([entry]) => setGraphWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  if (!data.nodes.length) {
    return (
      <Card title="Co-Mover Network" subtitle="1995–2026" valence="neutral">
        <p className="chart-note">No co-mover pairs found with current filters.</p>
      </Card>
    );
  }

  // Compute node degree (total motion count) for sizing
  const degree: Record<string, number> = {};
  for (const link of data.links) {
    degree[link.source as string] = (degree[link.source as string] ?? 0) + link.value;
    degree[link.target as string] = (degree[link.target as string] ?? 0) + link.value;
  }
  const maxDeg = Math.max(...Object.values(degree), 1);

  const graphData = {
    nodes: data.nodes.map((n) => ({
      id: n.id,
      name: n.id,
      val: ((degree[n.id] ?? 0) / maxDeg) * 18 + 4,
    })),
    links: data.links.map((l) => ({
      source: l.source,
      target: l.target,
      value: l.value,
    })),
  };

  return (
    <Card title="Co-Mover Network" subtitle="Active councillors, 1995–2026" valence="neutral">
      <div ref={containerRef} style={{ width: "100%", height: 420, borderRadius: 8, overflow: "hidden", background: "#0f172a" }}>
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          width={graphWidth}
          height={420}
          onEngineStop={handleEngineStop}
          cooldownTicks={150}
          backgroundColor="#0f172a"
          nodeLabel="name"
          nodeColor={() => "#60a5fa"}
          nodeVal={(n: { val?: number }) => n.val ?? 6}
          linkWidth={(l: { value?: number }) => Math.sqrt((l.value ?? 1))}
          linkColor={() => "rgba(148,163,184,0.4)"}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          nodeCanvasObject={(node: { x?: number; y?: number; name?: string; val?: number }, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const label = (node.name as string) ?? "";
            const r = Math.sqrt((node.val ?? 6)) * 2;
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
            ctx.fillStyle = "#3b82f6";
            ctx.fill();
            ctx.strokeStyle = "#93c5fd";
            ctx.lineWidth = 1;
            ctx.stroke();
            if (globalScale > 1.2 || r > 5) {
              const fontSize = Math.max(10 / globalScale, 3);
              ctx.font = `${fontSize}px sans-serif`;
              ctx.fillStyle = "#f1f5f9";
              ctx.textAlign = "center";
              ctx.fillText(label.split(" ").slice(-1)[0], node.x ?? 0, (node.y ?? 0) + r + fontSize);
            }
          }}
        />
      </div>
      <div className="comover-legend">
        <p className="chart-note">
          Node size = total motions moved or seconded. Arrow direction = mover → seconder.
          Edge thickness = frequency of co-proposing.
        </p>
      </div>
      <div className="comover-table-wrap">
        <table className="exception-table">
          <thead>
            <tr><th>Mover</th><th>Seconder</th><th>Count</th></tr>
          </thead>
          <tbody>
            {data.pairs.slice(0, 12).map((p, i) => (
              <tr key={i}>
                <td>{p.mover_name}</td>
                <td>{p.seconder_name}</td>
                <td>{p.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
