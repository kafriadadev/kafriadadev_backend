import { getRequestConfig } from "next-intl/server";

/**
 * Every string a person reads comes from messages/<locale>.json. English is the
 * only language at launch; adding one (Hausa first) is a new file plus a line
 * in LOCALES, with no change to any screen.
 */
export const LOCALES = ["en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";

export default getRequestConfig(async () => {
  const locale = DEFAULT_LOCALE;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
