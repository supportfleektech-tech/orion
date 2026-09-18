import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Shortcuts } from "../components/Shortcuts";

describe("keyboard shortcut help", () => {
  it("opens on ?", async () => {
    const user = userEvent.setup();
    render(<Shortcuts />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.keyboard("?");
    expect(await screen.findByRole("dialog", { name: /keyboard shortcuts/i })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Shortcuts />);
    await user.keyboard("?");
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("does not steal ? from someone typing a question", async () => {
    const user = userEvent.setup();
    render(
      <>
        <input aria-label="message" />
        <Shortcuts />
      </>,
    );

    await user.click(screen.getByLabelText("message"));
    await user.keyboard("why?");

    expect(screen.getByLabelText("message")).toHaveValue("why?");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not steal ? from a textarea either", async () => {
    const user = userEvent.setup();
    render(
      <>
        <textarea aria-label="composer" />
        <Shortcuts />
      </>,
    );

    await user.click(screen.getByLabelText("composer"));
    await user.keyboard("what now?");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("documents the palette and voice bindings the app actually registers", async () => {
    const user = userEvent.setup();
    render(<Shortcuts />);
    await user.keyboard("?");

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Open the command palette");
    expect(dialog).toHaveTextContent("Start or stop voice input");
    expect(dialog).toHaveTextContent("Send the message");
  });
});
