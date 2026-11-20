import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import TravelerProfileForm, { dietLabels, dietOptions } from "../components/TravelerProfile.jsx";

describe("traveler dietary needs", () => {
  it("saves the chosen restrictions as a list of backend tokens", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<TravelerProfileForm language="en" firstVisit onSave={onSave} onCancel={() => {}} />);

    await user.click(screen.getByRole("checkbox", { name: "Halal" }));
    await user.click(screen.getByRole("checkbox", { name: "No beef" }));
    await user.click(screen.getByRole("checkbox", { name: "Halal" }));
    await user.click(screen.getByRole("checkbox", { name: "No pork" }));
    await user.click(screen.getByRole("button", { name: "Save and start" }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ diet: ["no beef", "no pork"], name: "" }));
  });

  it("keeps known saved values and drops unknown ones", () => {
    render(<TravelerProfileForm language="ja" initial={{ diet: ["halal", "kosher"] }} onSave={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole("checkbox", { name: "ハラール" })).toBeChecked();
    expect(screen.getAllByRole("checkbox").filter((box) => box.checked)).toHaveLength(1);
  });

  it("has a label for every option in every language", () => {
    for (const language of ["ko", "en", "ja", "zh-Hans", "zh-Hant"]) {
      const labels = dietLabels(language);
      expect(dietOptions.every((value) => labels[value])).toBe(true);
    }
  });
});
