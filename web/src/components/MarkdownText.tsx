import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = { text: string; className?: string };

export function MarkdownText({ text, className }: Props) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 leading-7">{children}</p>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-bronze/70 pl-3 italic text-ink-700">{children}</blockquote>
          ),
          li: ({ children }) => <li className="ml-5 list-disc">{children}</li>
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
