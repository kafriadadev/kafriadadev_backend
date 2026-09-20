/**
 * Kobo to a printed amount, in one place.
 *
 * Money is whole kobo everywhere else and is only turned into naira here, at the
 * last step before a person reads it. Integer arithmetic only: no float ever
 * holds an amount, so 250000 is "₦2,500.00" and never "₦2499.9999999".
 */
export function formatNaira(kobo: number): string {
  const naira = Math.trunc(kobo / 100);
  const rest = String(Math.abs(kobo % 100)).padStart(2, "0");
  // Manual grouping: Intl differs between runtimes, and Opera Mini renders
  // whatever the server sent, so the server should send it finished.
  const grouped = String(Math.abs(naira)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${kobo < 0 ? "-" : ""}₦${grouped}.${rest}`;
}
