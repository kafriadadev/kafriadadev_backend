import type { Position } from "@/components/icons";

/** The position line on a player card: the API's football positions, by unit. */
export const POSITION_UNIT: Record<string, Position> = {
  Goalkeeper: "GK",
  "Centre-back": "DF",
  "Full-back": "DF",
  "Defensive midfielder": "MF",
  "Central midfielder": "MF",
  "Attacking midfielder": "MF",
  Winger: "FW",
  Striker: "FW",
};

export function positionUnit(position: string | null | undefined): Position | null {
  return position ? POSITION_UNIT[position] ?? null : null;
}
