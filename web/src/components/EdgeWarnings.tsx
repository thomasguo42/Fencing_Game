type Props = {
  warningAttrs: string[];
};

const MAP: Record<string, string> = {
  stamina: "top-0 left-0 right-0 h-2",
  skill: "top-0 bottom-0 right-0 w-2",
  mind: "bottom-0 left-0 right-0 h-2",
  academics: "top-0 bottom-0 left-0 w-2",
  social: "top-0 right-0 h-10 w-10 rounded-bl-2xl",
  finance: "bottom-0 left-0 h-10 w-10 rounded-tr-2xl"
};

export function EdgeWarnings({ warningAttrs }: Props) {
  if (warningAttrs.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-40">
      {warningAttrs.map((attr) => (
        <div
          key={attr}
          className={`absolute ${MAP[attr] ?? ""} bg-danger/85 shadow-glowDanger`}
          aria-hidden
        />
      ))}
    </div>
  );
}
