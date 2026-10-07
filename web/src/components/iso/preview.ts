/* Every figure in its typical states, for the style guide and scripts/iso-preview.mjs. */
import { howCard, howRegister, howScan, type Figure } from "./figures.ts";
import { cardPrinter, doneStage, ground, heldCard, noSignal, outOfPlay, rollout, serverDown, squadBench, varBooth } from "./scenes.ts";

export const PREVIEW: Record<string, Figure> = {
  "how-register": howRegister(),
  "how-card": howCard(),
  "how-scan": howScan(),
  "done-stage": doneStage(),
  "ground-new": ground({ profile: true, card: true, photo: false, club: false }),
  "ground-review": ground({ profile: true, card: true, photo: "wait", club: true }),
  "ground-all": ground({ profile: true, card: true, photo: true, club: true }),
  "booth-none": varBooth("none"),
  "booth-review": varBooth("under_review"),
  "booth-approved": varBooth("approved"),
  "booth-rejected": varBooth("rejected"),
  "out-of-play": outOfPlay(),
  "no-signal": noSignal(),
  "server-down": serverDown(),
  "held-yellow": heldCard("yellow"),
  "held-red": heldCard("red"),
  "bench-4": squadBench(4),
  "printer-5": cardPrinter(5),
  "rollout": rollout(Array.from({ length: 27 }, (_, i) => ({ key: `l${i}`, live: [0, 3, 4, 9, 14].includes(i) }))),
};
