'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import type { GraphPayload } from './brain';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

// Node colour by entity type (plan step 10).
const TYPE_COLOURS: Record<string, string> = {
  Person: '#2563eb',
  Role: '#7c3aed',
  Department: '#0891b2',
  Process: '#16a34a',
  Step: '#65a30d',
  System: '#db2777',
  Artifact: '#64748b',
  Rule: '#1d4ed8',
  Exception: '#be123c',
  Issue: '#dc2626',
  Product: '#ea580c',
  Vendor: '#a16207',
  Customer: '#0d9488',
  Licensor: '#9333ea',
  Metric: '#ca8a04',
  Decision: '#4f46e5',
};

type Node = NodeObject<{ id: string; name: string; type: string; source_count: number }>;
type Link = LinkObject<Node, { rel_type: string; weight: number }>;

export function CommunityGraph({
  graph,
  onSelect,
}: {
  graph: GraphPayload;
  onSelect: (entityId: string) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods<Node, Link> | undefined>(undefined);
  const [width, setWidth] = useState(640);
  const [positions, setPositions] = useState<string>('{}');
  const height = 460;

  const data = useMemo(
    () => ({
      nodes: graph.nodes.map((node) => ({ ...node })) as Node[],
      links: graph.edges.map((edge) => ({ ...edge })) as Link[],
    }),
    [graph],
  );

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.floor(entries[0]?.contentRect.width ?? 640);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Publish node screen positions once the layout settles so the browser
  // test (and assistive tooling) can find a node on the canvas.
  const publishPositions = useCallback(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const out: Record<string, [number, number]> = {};
    for (const node of data.nodes) {
      if (node.x === undefined || node.y === undefined) continue;
      const point = fg.graph2ScreenCoords(node.x, node.y);
      out[String(node.id)] = [Math.round(point.x), Math.round(point.y)];
    }
    setPositions(JSON.stringify(out));
  }, [data]);

  const large = graph.nodes.length > 500;

  return (
    <div className="space-y-2">
      {graph.notice && (
        <p className="text-xs text-amber-800" data-testid="graph-notice">
          {graph.notice}
        </p>
      )}
      <div
        ref={wrapRef}
        data-testid="community-graph"
        data-node-positions={positions}
        className="overflow-hidden rounded border bg-white"
        style={{ height }}
      >
        <ForceGraph2D
          ref={fgRef as never}
          graphData={data}
          width={width}
          height={height}
          nodeId="id"
          nodeLabel={(raw: NodeObject) => {
            const node = raw as Node;
            return `${node.name} (${node.type})`;
          }}
          nodeColor={(raw: NodeObject) => {
            const node = raw as Node;
            return TYPE_COLOURS[node.type] ?? '#334155';
          }}
          nodeVal={(raw: NodeObject) => {
            const node = raw as Node;
            return 1 + Math.min(node.source_count, 6);
          }}
          linkWidth={(raw: LinkObject) => Math.min(1 + (raw as Link).weight, 8)}
          linkColor={() => 'rgba(100,116,139,0.5)'}
          linkLabel={(raw: LinkObject) => (raw as Link).rel_type}
          cooldownTicks={large ? 60 : 150}
          warmupTicks={large ? 20 : 0}
          onEngineStop={() => {
            const fg = fgRef.current;
            fg?.zoomToFit(0, 40);
            if (fg && fg.zoom() > 3) fg.zoom(3, 0);
            window.setTimeout(publishPositions, 50);
          }}
          onZoomEnd={publishPositions}
          nodeCanvasObjectMode={() => (large ? undefined : 'after')}
          nodeCanvasObject={(raw: NodeObject, ctx: CanvasRenderingContext2D, scale: number) => {
            const node = raw as Node;
            if (large || node.x === undefined || node.y === undefined) return;
            const size = 11 / scale;
            ctx.font = `${size}px sans-serif`;
            ctx.fillStyle = '#0f172a';
            ctx.textAlign = 'center';
            ctx.fillText(node.name, node.x, node.y + 8 + size);
          }}
          onNodeClick={(raw: NodeObject) => {
            const node = raw as Node;
            return onSelect(String(node.id));
          }}
        />
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">
          List of the {graph.nodes.length} things in this graph
        </summary>
        <ul className="mt-2 flex flex-wrap gap-1">
          {graph.nodes.map((node) => (
            <li key={node.id}>
              <button
                type="button"
                className="rounded border px-2 py-0.5 text-xs hover:bg-muted"
                onClick={() => onSelect(node.id)}
              >
                {node.name}
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
