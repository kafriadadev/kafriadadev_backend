/** Nothing to show yet, with the next step if there is one. */
export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <section>
      <p><strong>{title}</strong></p>
      {children}
    </section>
  );
}
