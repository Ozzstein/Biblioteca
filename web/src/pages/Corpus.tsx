import { useEffect, useState } from 'react';
import { FileText } from 'lucide-react';

interface CorpusStats {
  total_documents: number;
  total_chunks: number;
  total_tokens: number;
  pending_files: number;
  recent_documents: Array<{
    doc_id: string;
    path: string;
    status: string;
    chunks: number;
    processed_at?: string;
  }>;
}

export default function Corpus() {
  const [stats, setStats] = useState<CorpusStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/corpus/stats')
      .then((res) => res.json())
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch corpus stats:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-foreground">Corpus</h2>
        <p className="text-muted-foreground mt-1">Document management and statistics</p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="Documents" value={stats?.total_documents || 0} />
        <StatCard title="Chunks" value={stats?.total_chunks || 0} />
        <StatCard title="Tokens" value={(stats?.total_tokens || 0).toLocaleString()} />
        <StatCard title="Pending" value={stats?.pending_files || 0} variant="warning" />
      </div>

      <div className="bg-card rounded-lg border border-border">
        <div className="p-6 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground">Recent Documents</h3>
        </div>
        <div className="divide-y divide-border">
          {stats?.recent_documents?.length ? (
            stats.recent_documents.map((doc) => (
              <div key={doc.doc_id} className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText className="w-5 h-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium text-foreground">{doc.doc_id}</p>
                    <p className="text-xs text-muted-foreground">{doc.path}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">{doc.chunks} chunks</p>
                    {doc.processed_at && (
                      <p className="text-xs text-muted-foreground">
                        {new Date(doc.processed_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  <StatusBadge status={doc.status} />
                </div>
              </div>
            ))
          ) : (
            <div className="p-8 text-center text-muted-foreground">
              No documents yet. Drop files in raw/inbox/ to start processing.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  variant = 'default',
}: {
  title: string;
  value: number | string;
  variant?: 'default' | 'warning';
}) {
  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <p className="text-sm text-muted-foreground">{title}</p>
      <p className={`text-2xl font-bold mt-1 ${variant === 'warning' ? 'text-yellow-500' : 'text-foreground'}`}>
        {value}
      </p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    completed: 'bg-green-500/10 text-green-500',
    processing: 'bg-blue-500/10 text-blue-500',
    pending: 'bg-yellow-500/10 text-yellow-500',
    error: 'bg-red-500/10 text-red-500',
  };

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${variants[status] || variants.pending}`}>
      {status}
    </span>
  );
}
