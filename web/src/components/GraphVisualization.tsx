import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';

interface Node {
  id: string;
  type: string;
  name: string;
  group: number;
}

interface Link {
  source: string;
  target: string;
  type: string;
}

interface GraphData {
  nodes: Node[];
  links: Link[];
}

interface GraphVisualizationProps {
  width?: number;
  height?: number;
}

const COLORS = [
  '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981',
  '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#d946ef',
];

export default function GraphVisualization({ width = 800, height = 600 }: GraphVisualizationProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [nodeTypes, setNodeTypes] = useState<string[]>([]);

  useEffect(() => {
    fetch('/api/graph/full')
      .then(res => res.json())
      .then((graphData: GraphData) => {
        setData(graphData);
        const types = Array.from(new Set(graphData.nodes.map((n: Node) => n.type)));
        setNodeTypes(types);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load graph:', err);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (loading || data.nodes.length === 0 || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const g = svg.append('g');

    const simulation = d3.forceSimulation(data.nodes as any)
      .force('link', d3.forceLink(data.links as any).id((d: any) => d.id).distance(150))
      .force('charge', d3.forceManyBody().strength(-500))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(30));

    const link = g.append('g')
      .attr('stroke', '#94a3b8')
      .attr('stroke-opacity', 0.6)
      .selectAll('line')
      .data(data.links)
      .join('line')
      .attr('stroke-width', 1.5);

    const node = g.append('g')
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 2)
      .selectAll('circle')
      .data(data.nodes)
      .join('circle')
      .attr('r', 12)
      .attr('fill', (_: any, i: number) => COLORS[i % COLORS.length])
      .attr('cursor', 'pointer');

    node.append('title')
      .text((d: any) => `${d.name} (${d.type})`);

    node.on('click', (_: any, d: any) => {
      setSelectedNode(d as Node);
    });

    const labels = g.append('g')
      .selectAll('text')
      .data(data.nodes)
      .join('text')
      .text((d: any) => d.name.length > 15 ? d.name.substring(0, 12) + '...' : d.name)
      .attr('font-size', '10px')
      .attr('fill', '#cbd5e1')
      .attr('dx', 15)
      .attr('dy', 4);

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node
        .attr('cx', (d: any) => d.x)
        .attr('cy', (d: any) => d.y);

      labels
        .attr('x', (d: any) => d.x)
        .attr('y', (d: any) => d.y);
    });

    return () => {
      simulation.stop();
    };
  }, [data, loading, width, height]);

  if (loading) {
    return <div className="text-muted-foreground text-center py-20">Loading graph...</div>;
  }

  if (data.nodes.length === 0) {
    return <div className="text-muted-foreground text-center py-20">No graph data available. Ingest documents first.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="bg-card rounded-lg border border-border p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-foreground">Knowledge Graph Visualization</h3>
          <div className="flex items-center gap-2 flex-wrap">
            {nodeTypes.map((type, idx) => (
              <div key={type} className="flex items-center gap-1 text-xs">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                />
                <span className="text-muted-foreground capitalize">{type}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="border border-border rounded-md overflow-hidden">
          <svg
            ref={svgRef}
            width="100%"
            height={height}
            className="bg-background"
          />
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Click and drag nodes to rearrange • Click node to see details
        </p>
      </div>

      {selectedNode && (
        <div className="bg-card rounded-lg border border-border p-4">
          <h4 className="text-md font-semibold text-foreground mb-2">
            {selectedNode.name}
          </h4>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">Type:</dt>
            <dd className="text-foreground capitalize">{selectedNode.type}</dd>
            <dt className="text-muted-foreground">ID:</dt>
            <dd className="text-foreground font-mono text-xs">{selectedNode.id}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
