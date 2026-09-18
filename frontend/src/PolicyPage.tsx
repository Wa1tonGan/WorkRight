import { useEffect, useState } from "react";
import { api, type PolicyDocument } from "./api";

export default function PolicyPage({ onBack }: { onBack: () => void }) {
  const [docs, setDocs] = useState<PolicyDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .policy()
      .then(setDocs)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load"));
  }, []);

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <div>
          <div className="brand">Knowledge base</div>
          <div className="who">
            what the agent can cite — every chunk is embedded and searchable
          </div>
        </div>
        <button className="ghost" onClick={onBack}>
          ← Back to chat
        </button>
      </header>

      <main className="chat-main policy-main">
        {error && <div className="error inline">{error}</div>}
        {!docs && !error && <div className="bubble assistant typing">loading…</div>}
        {docs?.map((doc) => (
          <section key={doc.title} className="doc-card">
            <div className="doc-head">
              <h2>{doc.title}</h2>
              <div className="badges">
                <span className="badge type">{doc.source_type}</span>
                <span className="badge">{doc.version}</span>
                {doc.effective_from && (
                  <span className="badge">
                    in force {doc.effective_from}
                    {doc.effective_to ? ` → ${doc.effective_to}` : ""}
                  </span>
                )}
                <span className="badge">{doc.chunk_count} chunks</span>
              </div>
              {doc.authority && <div className="doc-authority">{doc.authority}</div>}
            </div>

            <div className="chunks">
              {doc.chunks.map((c) => (
                <details key={c.chunk_id} className="chunk">
                  <summary>
                    <code>{c.chunk_id}</code>
                    <span className="chunk-topic">{c.topic}</span>
                    {c.section && <span className="badge small">§{c.section}</span>}
                  </summary>
                  <pre className="chunk-text">{c.text}</pre>
                  {c.embedding && (
                    <details className="coords">
                      <summary>
                        coordinates ({c.embedding.length}-d)
                        <span className="coord-preview">
                          [{c.embedding.slice(0, 3).map((n) => n.toFixed(3)).join(", ")}, …]
                        </span>
                      </summary>
                      <div className="coord-note">
                        These {c.embedding.length} numbers ARE the meaning of the
                        text above — BGE-M3's fingerprint. Search compares this
                        vector against the question's vector; the text is only
                        what gets quoted back.
                      </div>
                      <pre className="coord-text">
                        {Array.from({ length: Math.ceil(c.embedding.length / 8) },
                          (_, row) =>
                            c.embedding!
                              .slice(row * 8, row * 8 + 8)
                              .map((n) => n.toFixed(4).padStart(9))
                              .join(" "),
                        ).join("\n")}
                      </pre>
                    </details>
                  )}
                </details>
              ))}
            </div>
          </section>
        ))}
      </main>
    </div>
  );
}
