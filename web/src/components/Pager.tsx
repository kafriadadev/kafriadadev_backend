import { Pager as P } from "./ui/Pager";

/** The old Pager on the new one. */
export function Pager({ page, prev, next }: { page: number; prev?: string | null; next?: string | null }) {
  return <P label={`Page ${page}`} prev={prev} next={next} labels={{ prev: "Previous", next: "Next" }} />;
}
