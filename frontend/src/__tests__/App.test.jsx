import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App.jsx";

afterEach(() => vi.unstubAllGlobals());

it("shows a local sample and preserves chat state without requesting the backend", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  const user = userEvent.setup();
  const open = () => user.click(screen.getByRole("button", { name: "Chat" }));

  await open();
  expect(screen.getByRole("heading", { name: "Busan AI" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Half a day by the sea" }));
  expect(screen.getByRole("textbox")).toHaveValue("Half a day by the sea");
  await user.click(screen.getByRole("button", { name: "Send" }));
  expect(screen.queryByRole("button", { name: "Half a day by the sea" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Sample itinerary" })).toBeVisible();
  const stop = screen.getAllByRole("listitem")[1];
  expect(stop).toHaveTextContent("Fixed");
  await user.click(within(stop).getByRole("button"));
  await user.type(screen.getByRole("textbox"), "Add a market");
  await user.click(screen.getByRole("button", { name: "Collapse chat" }));
  await user.click(screen.getByRole("button", { name: "Itinerary" }));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Sample itinerary" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Home" }));
  expect(screen.queryByRole("heading", { name: "Sample itinerary" })).not.toBeInTheDocument();
  await open();
  expect(screen.getByRole("textbox")).toHaveValue("Add a market");
  expect(screen.getByText("Half a day by the sea")).toBeVisible();
  expect(within(stop).getByRole("button")).toHaveAttribute("aria-pressed", "true");
  await user.click(screen.getByRole("button", { name: "Send" }));
  expect(screen.getByText("Add a market")).toBeVisible();
  expect(fetchMock).not.toHaveBeenCalled();
});
