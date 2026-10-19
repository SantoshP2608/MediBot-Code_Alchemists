import './SplitText.css';

// Animate on mount only: existing replies keep their position when chat updates.
export default function SplitText({ text }) {
  if (typeof text !== 'string') return text;
  const parts = text.split(/(\s+)/);
  const wordCount = parts.filter((part) => part && !/^\s+$/.test(part)).length;
  const step = Math.min(30, 700 / Math.max(1, wordCount - 1));
  let index = 0;

  return <span className="split-reply" key={text}>{parts.map((part, position) => {
    if (!part || /^\s+$/.test(part)) return part;
    return <span className="split-reply-word" key={position}
      style={{ '--split-delay': `${index++ * step}ms` }}>{part}</span>;
  })}</span>;
}
