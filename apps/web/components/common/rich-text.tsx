import * as React from "react";
import { cn } from "@/components/ui/utils";

/**
 * Renders assistant-authored text safely.
 *
 * The backend only ever emits plain text with a tiny subset of markdown
 * (`**bold**`, `` `code` ``, `- ` bullets and blank-line paragraphs). We parse
 * that subset into React nodes — never dangerouslySetInnerHTML — so a hostile
 * dataset value or prompt-injected string can never become live markup.
 */
export function RichText({ text, className }: { text: string; className?: string }) {
  const blocks = React.useMemo(() => splitBlocks(text ?? ""), [text]);
  return (
    <div className={cn("space-y-2.5 text-[13.5px] leading-relaxed text-ink/90", className)}>
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          <ul key={index} className="space-y-1 pl-1">
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex} className="flex gap-2">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-brand/70" />
                <span>{inline(item)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p key={index}>{inline(block.text)}</p>
        ),
      )}
    </div>
  );
}

type Block = { kind: "paragraph"; text: string } | { kind: "list"; items: string[] };

function splitBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      continue;
    }
    if (!line) {
      flushList();
      flushParagraph();
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushList();
  flushParagraph();
  return blocks;
}

const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`)/g;

function inline(text: string): React.ReactNode[] {
  return text.split(TOKEN).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={index} className="rounded bg-line/[0.07] px-1 py-0.5 font-mono text-[12px] text-ink/80">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}
