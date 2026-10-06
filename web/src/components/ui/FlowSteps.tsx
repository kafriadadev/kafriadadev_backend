import { getTranslations } from "next-intl/server";
import { Stepper } from "./Stepper";

/** The registration run, AUT-01 → AUT-02 → AUT-03, shown on each of its screens. */
export async function FlowSteps({ current }: { current: 0 | 1 | 2 }) {
  const t = await getTranslations();
  const steps = t.raw("flow.steps") as string[];
  return (
    <div className="mb-8">
      <Stepper
        steps={steps}
        current={current}
        label={t("flow.label")}
        progressText={t("ui.stepOf", { current: current + 1, total: steps.length })}
      />
    </div>
  );
}
