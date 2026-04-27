import { useState } from 'react';
import { MessageSquare, Send, Loader2, BookOpen, FileText, Network } from 'lucide-react';

interface Citation {
  type: string;
  source: string;
  page?: number;
  section?: string;
}

interface QueryResult {
  answer: string;
  citations: Citation[];
  context: Record<string, any>;
  latency_ms: number;
}

export default function Query() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState('hybrid');
  const [quality, setQuality] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          mode,
          quality,
        }),
      });

      if (!response.ok) {
        throw new Error('Query failed');
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error('Query error:', err);
      setResult({
        answer: 'An error occurred while processing your query. Please try again.',
        citations: [],
        context: {},
        latency_ms: 0,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-foreground">Query</h2>
        <p className="text-muted-foreground mt-1">Ask questions about your research corpus</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="bg-card rounded-lg border border-border p-6">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask a question about battery research... (e.g., 'What causes LFP capacity fade?')"
            className="w-full h-32 bg-background border border-border rounded-md p-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          />

          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center gap-4">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Mode</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="px-3 py-2 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="hybrid">Hybrid</option>
                  <option value="wiki-first">Wiki First</option>
                  <option value="evidence-first">Evidence First</option>
                  <option value="graph-first">Graph First</option>
                </select>
              </div>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={quality}
                  onChange={(e) => setQuality(e.target.checked)}
                  className="w-4 h-4 rounded border-border"
                />
                <span className="text-sm text-foreground">Quality (Opus)</span>
              </label>
            </div>

            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="px-6 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Ask
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      {result && (
        <div className="space-y-4">
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <MessageSquare className="w-5 h-5" />
                Answer
              </h3>
              <span className="text-xs text-muted-foreground">
                {result.latency_ms.toFixed(0)}ms
              </span>
            </div>
            <div className="prose prose-invert max-w-none">
              <p className="text-foreground whitespace-pre-wrap">{result.answer}</p>
            </div>
          </div>

          {result.citations.length > 0 && (
            <div className="bg-card rounded-lg border border-border p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <BookOpen className="w-5 h-5" />
                Citations ({result.citations.length})
              </h3>
              <div className="space-y-2">
                {result.citations.map((citation, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-3 p-3 bg-background rounded-md"
                  >
                    {citation.type === 'evidence' ? (
                      <FileText className="w-4 h-4 text-muted-foreground" />
                    ) : citation.type === 'wiki' ? (
                      <BookOpen className="w-4 h-4 text-muted-foreground" />
                    ) : (
                      <Network className="w-4 h-4 text-muted-foreground" />
                    )}
                    <div className="flex-1">
                      <p className="text-sm text-foreground">{citation.source}</p>
                      {citation.page && (
                        <p className="text-xs text-muted-foreground">Page {citation.page}</p>
                      )}
                      {citation.section && (
                        <p className="text-xs text-muted-foreground capitalize">{citation.section}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
