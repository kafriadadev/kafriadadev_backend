/** The style guide is served in development, or by a review build started with STYLEGUIDE=1. */
export function styleguideEnabled() {
  return process.env.NODE_ENV !== "production" || process.env.STYLEGUIDE === "1";
}
