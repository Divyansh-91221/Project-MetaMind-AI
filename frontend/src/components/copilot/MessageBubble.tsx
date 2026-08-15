import { Link } from 'react-router-dom';
import type { ChatMessage } from '@/types';

/**
 * A single chat turn.
 *
 * Assistant answers render lightweight markdown (bold, bullets) without pulling in a markdown
 * dependency - the backend deliberately produces a small, predictable subset.
 */
export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return <div className="message user">{message.content}</div>;
  }

  return (
    <div className="message assistant">
      {renderLines(message.content)}

      {message.warnings && message.warnings.length > 0 && (
        <div className="banner" style={{ marginTop: 10 }}>
          {message.warnings.map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}

      {message.evidence && message.evidence.length > 0 && (
        <div className="faint small" style={{ marginTop: 8 }}>
          {message.evidence.length} piece(s) of evidence ·{' '}
          {message.evidence.filter((item) => item.inferred).length} inferred
        </div>
      )}
    </div>
  );
}

function renderLines(content: string) {
  return content.split('\n').map((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return <br key={index} />;

    if (trimmed.startsWith('**') && trimmed.endsWith('**')) {
      return <h3 key={index}>{trimmed.replace(/\*\*/g, '')}</h3>;
    }
    if (trimmed.startsWith('- ')) {
      return (
        <div key={index} style={{ paddingLeft: 12 }}>
          • {inline(trimmed.slice(2))}
        </div>
      );
    }
    return <div key={index}>{inline(trimmed)}</div>;
  });
}

/** Bold spans, inline code and asset links. */
function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|urn:emc:[^\s,)]+)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith('urn:emc:')) {
      return (
        <Link key={index} to={`/assets?urn=${encodeURIComponent(part)}`} className="mono small">
          {part.split(':').slice(4).join(':')}
        </Link>
      );
    }
    return <span key={index}>{part}</span>;
  });
}
