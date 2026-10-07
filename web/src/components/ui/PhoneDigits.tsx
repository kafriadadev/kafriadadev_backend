"use client";

import { caretAfterDigits, formatNigerianPhone } from "@/lib/phone";

/**
 * The phone field's input. With JavaScript it groups the number as it is
 * typed (0803 123 4567) and keeps the caret where the person was typing; the
 * value stays uncontrolled, so a form posts exactly what is on screen. Without
 * JavaScript it is a plain tel input. `data-phone` lets public/enhance.js do the
 * same on a page that ships no framework.
 */
export function PhoneDigits(props: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "onInput">) {
  return (
    <input
      {...props}
      type="tel"
      data-phone=""
      onInput={(e) => {
        const el = e.currentTarget;
        const before = el.value.slice(0, el.selectionStart ?? el.value.length).replace(/\D/g, "").length;
        const next = formatNigerianPhone(el.value);
        if (next === el.value) return;
        el.value = next;
        const at = caretAfterDigits(next, before);
        el.setSelectionRange(at, at);
      }}
    />
  );
}
