import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App.jsx";

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

it("keeps the itinerary until an AI suggestion is applied and rejects stale suggestions", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  const user = userEvent.setup();
  const select = (name) => user.click(screen.getByRole("button", { name, exact: true }));
  expect(screen.queryByRole("button", { name: "2. Jagalchi Market" })).not.toBeInTheDocument();

  await select("Itinerary");
  await select("Get an AI itinerary");
  await user.click(screen.getByLabelText(/Nampo · Yeongdo/));
  await user.click(screen.getByLabelText("Arts and culture"));
  await select("Home");
  await select("Itinerary");
  expect(screen.getByLabelText(/Nampo · Yeongdo/)).toBeChecked();
  await select("Create itinerary");
  await screen.findByRole("button", { name: "Edit with AI · Jagalchi Market" });
  const course = JSON.parse(localStorage.getItem("busannow.course")).plan;

  await select("Edit with AI · Jagalchi Market");
  expect(screen.getByText("2 · Jagalchi Market")).toBeVisible();
  await user.type(screen.getByRole("textbox"), "Try a different market");
  await select("Send");
  await screen.findByRole("button", { name: "Apply to itinerary" });
  await user.type(screen.getByRole("textbox"), "Is there another option?");
  await select("Send");
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Apply to itinerary" })).toHaveLength(2));

  expect(screen.getByRole("button", { name: "2. Jagalchi Market" })).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Apply to itinerary" })[0]);
  expect(screen.getByRole("button", { name: "2. Gukje Market" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Apply to itinerary" })).not.toBeInTheDocument();
  expect(screen.getByText("The itinerary changed. Request a new suggestion.")).toBeVisible();
  const saved = JSON.parse(localStorage.getItem("busannow.course")).plan;
  expect(saved.stops).toEqual(course.stops.map((stop, index) => index === 1
    ? { ...stop, place_id: "gukje-market" } : stop));

  await select("Itinerary");
  const stop = screen.getAllByRole("listitem")[1];
  expect(within(stop).getByRole("button", { pressed: true })).toHaveTextContent("Gukje Market");
  expect(fetchMock).not.toHaveBeenCalled();
});
