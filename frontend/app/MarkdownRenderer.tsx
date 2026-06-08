"use client";

import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
});

const Mermaid = ({ chart }: { chart: string }) => {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<boolean>(false);
  
  // Use a unique ID for each mermaid diagram to avoid conflicts
  const [containerId] = useState(`mermaid-${Math.random().toString(36).substring(2, 9)}`);

  useEffect(() => {
    const renderChart = async () => {
      try {
        const { svg } = await mermaid.render(containerId, chart);
        setSvg(svg);
        setError(false);
      } catch (err) {
        console.error('Mermaid rendering error:', err);
        setError(true);
      }
    };
    if (chart) {
      renderChart();
    }
  }, [chart, containerId]);

  if (error) {
    return <pre className="mermaid-error" style={{ color: 'red', fontSize: '12px', overflowX: 'auto', background: '#fee2e2', padding: '12px', borderRadius: '8px' }}><code>{chart}</code></pre>;
  }

  return <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} style={{ display: 'flex', justifyContent: 'center', background: '#fff', padding: '16px', borderRadius: '12px', border: '1px solid #e2e8f0', margin: '16px 0', overflowX: 'auto' }} />;
};

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="markdown-body" style={{ width: '100%' }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const isMermaid = match && match[1] === 'mermaid';

            if (!inline && isMermaid) {
              return <Mermaid chart={String(children).replace(/\n$/, '')} />;
            }

            return !inline ? (
              <pre style={{ background: '#0f172a', color: '#f8fafc', padding: '16px', borderRadius: '12px', overflowX: 'auto', fontSize: '13px', margin: '16px 0' }}>
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            ) : (
              <code className={className} {...props} style={{ background: '#f1f5f9', padding: '3px 6px', borderRadius: '6px', fontSize: '13px', color: '#db2777', fontWeight: 500 }}>
                {children}
              </code>
            );
          },
          table: ({ node, ...props }) => <div style={{ overflowX: 'auto', margin: '16px 0' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }} {...props} /></div>,
          th: ({ node, ...props }) => <th style={{ border: '1px solid #e2e8f0', padding: '10px 16px', background: '#f8fafc', fontWeight: 600, textAlign: 'left', color: '#334155' }} {...props} />,
          td: ({ node, ...props }) => <td style={{ border: '1px solid #e2e8f0', padding: '10px 16px', color: '#475569' }} {...props} />,
          a: ({ node, ...props }) => <a style={{ color: '#2563eb', textDecoration: 'underline', textUnderlineOffset: '2px' }} target="_blank" rel="noopener noreferrer" {...props} />,
          p: ({ node, ...props }) => <p style={{ marginBottom: '14px', lineHeight: 1.7, color: '#334155' }} {...props} />,
          ul: ({ node, ...props }) => <ul style={{ marginBottom: '14px', paddingLeft: '24px', listStyleType: 'disc', color: '#334155' }} {...props} />,
          ol: ({ node, ...props }) => <ol style={{ marginBottom: '14px', paddingLeft: '24px', listStyleType: 'decimal', color: '#334155' }} {...props} />,
          h1: ({ node, ...props }) => <h1 style={{ fontSize: '1.75em', fontWeight: 700, marginTop: '28px', marginBottom: '16px', color: '#0f172a' }} {...props} />,
          h2: ({ node, ...props }) => <h2 style={{ fontSize: '1.5em', fontWeight: 600, marginTop: '24px', marginBottom: '14px', color: '#0f172a' }} {...props} />,
          h3: ({ node, ...props }) => <h3 style={{ fontSize: '1.25em', fontWeight: 600, marginTop: '20px', marginBottom: '12px', color: '#0f172a' }} {...props} />,
          blockquote: ({ node, ...props }) => <blockquote style={{ borderLeft: '4px solid #cbd5e1', paddingLeft: '16px', margin: '16px 0', color: '#64748b', fontStyle: 'italic' }} {...props} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
