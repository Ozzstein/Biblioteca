import { useEffect, useState } from 'react';
import { Network } from 'lucide-react';

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
}

interface Entity {
  id: string;
  type: string;
  name: string;
  description?: string;
}

export default function Graph() {
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [selectedType, setSelectedType] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/graph/stats').then((res) => res.json()),
      fetch('/api/graph/entities?limit=100').then((res) => res.json()),
    ])
      .then(([statsData, entitiesData]) => {
        setStats(statsData);
        setEntities(entitiesData);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch graph data:', err);
        setLoading(false);
      });
  }, []);

  const filteredEntities =
    selectedType === 'all'
      ? entities
      : entities.filter((e) => e.type === selectedType);

  const nodeTypes = stats ? Object.keys(stats.nodes_by_type) : [];

  if (loading) {
    return <div className="text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-foreground">Knowledge Graph</h2>
        <p className="text-muted-foreground mt-1">Entity and relationship explorer</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="bg-card rounded-lg border border-border p-6">
          <p className="text-sm text-muted-foreground">Total Entities</p>
          <p className="text-2xl font-bold mt-1 text-foreground">{stats?.total_nodes || 0}</p>
        </div>
        <div className="bg-card rounded-lg border border-border p-6">
          <p className="text-sm text-muted-foreground">Total Relations</p>
          <p className="text-2xl font-bold mt-1 text-foreground">{stats?.total_edges || 0}</p>
        </div>
        <div className="bg-card rounded-lg border border-border p-6">
          <p className="text-sm text-muted-foreground">Entity Types</p>
          <p className="text-2xl font-bold mt-1 text-foreground">{nodeTypes.length}</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="bg-card rounded-lg border border-border">
          <div className="p-6 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground">Entities by Type</h3>
          </div>
          <div className="p-6 space-y-3">
            {stats?.nodes_by_type &&
              Object.entries(stats.nodes_by_type)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-sm text-foreground capitalize">{type}</span>
                    <span className="text-sm font-medium text-muted-foreground">{count}</span>
                  </div>
                ))}
          </div>
        </div>

        <div className="bg-card rounded-lg border border-border">
          <div className="p-6 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground">Relations by Type</h3>
          </div>
          <div className="p-6 space-y-3">
            {stats?.edges_by_type &&
              Object.entries(stats.edges_by_type)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-sm text-foreground capitalize">{type}</span>
                    <span className="text-sm font-medium text-muted-foreground">{count}</span>
                  </div>
                ))}
          </div>
        </div>
      </div>

      <div className="bg-card rounded-lg border border-border">
        <div className="p-6 border-b border-border">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-foreground">Entities</h3>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="px-3 py-2 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="all">All Types</option>
              {nodeTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="max-h-[400px] overflow-auto">
          <div className="divide-y divide-border">
            {filteredEntities.length ? (
              filteredEntities.map((entity) => (
                <div key={entity.id} className="p-4 hover:bg-accent/50 transition-colors">
                  <div className="flex items-start gap-3">
                    <Network className="w-5 h-5 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-foreground">{entity.name}</p>
                      <p className="text-xs text-muted-foreground capitalize">{entity.type}</p>
                      {entity.description && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {entity.description}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-muted-foreground">
                No entities found
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
