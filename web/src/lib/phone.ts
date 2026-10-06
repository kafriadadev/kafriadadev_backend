/**
 * Groups a Nigerian phone number for reading, as it is typed:
 *
 *   08031234567    -> 0803 123 4567
 *   8031234567     -> 803 123 4567     (the +234 is shown beside the field)
 *   +2348031234567 -> +234 803 123 4567
 *
 * Display only. The API normalises whatever arrives, so spaces never matter;
 * anything that is not a digit (or a leading +) is dropped, and digits beyond
 * a full number are kept as typed so nothing a person enters disappears.
 */
export function formatNigerianPhone(raw: string): string {
  const plus = raw.trim().startsWith("+");
  const digits = raw.replace(/\D/g, "");
  if (!digits) return plus ? "+" : "";

  let prefix = "";
  let rest = digits;
  if (plus || digits.startsWith("234")) {
    prefix = `${plus ? "+" : ""}${digits.slice(0, 3)}`;
    rest = digits.slice(3);
    if (!rest) return prefix;
  }
  // Local numbers carry a trunk 0: 0803 123 4567. Without it: 803 123 4567.
  const sizes = !prefix && rest.startsWith("0") ? [4, 3, 4] : [3, 3, 4];
  const groups: string[] = [];
  let i = 0;
  for (const size of sizes) {
    if (i >= rest.length) break;
    groups.push(rest.slice(i, i + size));
    i += size;
  }
  if (i < rest.length) groups[groups.length - 1] += rest.slice(i);
  return [prefix, ...groups].filter(Boolean).join(" ");
}

/** Where the caret belongs after formatting: after the same number of digits. */
export function caretAfterDigits(formatted: string, digitsBefore: number): number {
  if (digitsBefore <= 0) return formatted.startsWith("+") ? 1 : 0;
  let seen = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted[i])) seen++;
    if (seen === digitsBefore) return i + 1;
  }
  return formatted.length;
}
