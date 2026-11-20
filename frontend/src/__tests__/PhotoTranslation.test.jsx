import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import TranslationPage from "../components/TranslationPage.jsx";
import { getTranslationCopy } from "../constants/translationCopy.js";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it.each([
  ["image/png", 200, "Spiciness could not be confirmed."],
  ["image/jpeg", 404, "The uploaded photo could not be found. Try again."],
  ["image/jpeg", 422, "Choose a JPEG or PNG photo."],
  ["image/jpeg", 500, "The photo translation server encountered an error. Try again shortly."],
])("uploads a %s and handles translation status %i", async (type, status, expected) => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = () => "blob:photo-preview";
    static revokeObjectURL = () => {};
  });
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    disconnect() {}
  });
  const key = "photos/test.jpg";
  const uploadUrl = "https://s3.example.test/photos/test.jpg?signature=example";
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ upload_url: uploadUrl, key, expires_in: 300 })))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      key, language: "ja", items: [{
        text_ko: "김치찌개", translated: "キムチチゲ", bbox: { left: .1, top: .2, width: .3, height: .05 }, spicy: null,
      }],
    }), { status }));
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(
    <main className="travel-preview">
      <aside className="travel-chat">
        <div className="chat-grab" />
        <header className="chat-heading" />
        <TranslationPage active mode="photo" language="en" copy={getTranslationCopy("en")} />
      </aside>
    </main>,
  );
  const target = screen.getByRole("combobox", { name: "Translate into" });
  expect(within(target).getAllByRole("option").map((option) => option.value)).toEqual(["en", "ja", "zh-Hans", "zh-Hant"]);
  fireEvent.change(target, { target: { value: "ja" } });
  const file = new File(["photo"], "menu", { type });
  fireEvent.change(screen.getByLabelText("Upload photo"), { target: { files: [file] } });
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Translate image" }));
  expect(await screen.findByText(expected)).toBeVisible();

  const [[firstUrl, first], [secondUrl, second], [thirdUrl, third]] = fetchMock.mock.calls;
  expect(firstUrl).toMatch(/\/photo\/upload-url$/);
  expect(first.method).toBe("POST");
  expect(JSON.parse(first.body)).toEqual({ content_type: type });
  expect(secondUrl).toBe(uploadUrl);
  expect(second).toMatchObject({ method: "PUT", headers: { "Content-Type": type }, body: file });
  expect(thirdUrl).toMatch(/\/photo\/translate$/);
  expect(JSON.parse(third.body)).toEqual({ key, language: "ja" });

  if (status === 200) {
    const overlay = container.querySelector(".translation-image-overlay span");
    expect(overlay).toHaveTextContent("キムチチゲ");
    expect(overlay).toHaveStyle({ left: "10%", top: "20%", width: "30%", height: "5%" });
  } else {
    expect(screen.getByRole("button", { name: "Translate image" })).toBeEnabled();
  }
  window.localStorage.removeItem("busannow.photoTranslationTarget");
});
