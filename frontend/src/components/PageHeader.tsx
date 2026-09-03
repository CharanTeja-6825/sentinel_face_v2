import type { ReactNode } from "react";

/**
 * C's opening move: a small machine-voice stamp, then one human statement in the
 * display face. Every page hand-rolled its own `<h1> + <p class="mt-2 text-sm">`
 * pair, which is why three pages had a text-3xl title and a fourth had text-2xl.
 */
export default function PageHeader({
  stamp,
  title,
  children,
  aside,
}: {
  stamp: string;
  title: string;
  children?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div className="min-w-0">
        <p className="stamp mb-3 font-medium text-instruct">{stamp}</p>
        <h1 className="max-w-[18ch] text-3xl font-semibold">{title}</h1>
        {children && (
          <p className="mt-3 max-w-[58ch] text-sm text-muted-foreground">{children}</p>
        )}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </header>
  );
}
