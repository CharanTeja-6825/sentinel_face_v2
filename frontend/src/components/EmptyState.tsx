/**
 * Three different one-liners did this job before. An empty state is the system
 * saying what to do next, so it takes the instruct voice rather than grey filler.
 */
export default function EmptyState({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: string;
}) {
  return (
    <div className="border-l-2 border-l-border py-2.5 pl-3.5">
      <p className="text-sm text-muted-foreground">{children}</p>
      {action && <p className="mt-1 text-sm text-instruct">{action}</p>}
    </div>
  );
}
