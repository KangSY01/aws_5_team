import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import StopTimeEditor from "../components/StopTimeEditor.jsx";
import { getItineraryEditCopy } from "../constants/itineraryEditCopy.js";

if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
}

const stops = [
  ["a", "10:00", "11:00"],
  ["b", "11:30", "12:30"],
  ["c", "13:00", "14:00"],
].map(([stop_id, start, end]) => ({
  stop_id, place_id: stop_id, start: `2026-11-21T${start}:00+09:00`, end: `2026-11-21T${end}:00+09:00`,
}));

it("previews time and order, then submits both together", async () => {
  const save = vi.fn().mockResolvedValue(true);
  const close = vi.fn();
  render(<StopTimeEditor stops={stops} index={0} name="Busan Museum"
    copy={getItineraryEditCopy("en")} onClose={close} onSave={save} />);
  expect(screen.getByRole("button", { name: "Move up" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Move down" }));
  expect(screen.getByText("Position 2")).toBeVisible();
  expect(screen.getByLabelText("Start time")).toHaveValue("11:30");
  fireEvent.change(screen.getByLabelText("End time"), { target: { value: "13:15" } });
  expect(screen.getByText("Overlaps another visit")).toBeVisible();
  fireEvent.change(screen.getByLabelText("End time"), { target: { value: "12:15" } });
  expect(screen.queryByText("Overlaps another visit")).not.toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  const [saved] = save.mock.calls[0];
  expect(saved.map((stop) => stop.stop_id)).toEqual(["b", "a", "c"]);
  expect(saved[1]).toMatchObject({ start: stops[1].start, end: "2026-11-21T12:15:00+09:00" });
});

it("does not submit a draft when cancelled", () => {
  const save = vi.fn();
  const close = vi.fn();
  render(<StopTimeEditor stops={stops} index={2} name="Busan Museum"
    copy={getItineraryEditCopy("en")} onClose={close} onSave={save} />);
  expect(screen.getByRole("button", { name: "Move down" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Move up" }));
  fireEvent.change(screen.getByLabelText("End time"), { target: { value: "12:25" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(close).toHaveBeenCalledOnce();
  expect(save).not.toHaveBeenCalled();
});

it.each([
  [0, "Move down", "Move up", "Position 2", "Position 1"],
  [2, "Move up", "Move down", "Position 2", "Position 3"],
])("can return to the original position after moving from index %i", async (index, move, back, preview, original) => {
  const save = vi.fn();
  const close = vi.fn();
  render(<StopTimeEditor stops={stops} index={index} name="Busan Museum"
    copy={getItineraryEditCopy("en")} onClose={close} onSave={save} />);
  fireEvent.click(screen.getByRole("button", { name: move }));
  expect(screen.getByText(preview)).toBeVisible();
  const returnButton = screen.getByRole("button", { name: back });
  expect(returnButton).toBeEnabled();
  fireEvent.click(returnButton);
  expect(screen.getByText(original)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(save).not.toHaveBeenCalled();
});
