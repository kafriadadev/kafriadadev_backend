/** A plain submit button. It must sit inside the form it submits. */
export function SubmitButton({
  children,
  disabled,
  name,
  value,
}: {
  children: React.ReactNode;
  className?: string;
  pending?: string;
  detail?: string;
  disabled?: boolean;
  name?: string;
  value?: string;
}) {
  return (
    <button type="submit" disabled={disabled} name={name} value={value}>
      {children}
    </button>
  );
}
