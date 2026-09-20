import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { CommandPalette } from "../components/CommandPalette";

vi.mock("../lib/api", () => ({
  api: { killSwitch: vi.fn().mockResolvedValue({ enabled: true }) },
}));

import { api } from "../lib/api";

/** Renders the palette with a probe that reports the current route. */
function setup() {
  function Probe() {
    const location = useLocation();
    return <div data-testid="route">{location.pathname + location.search}</div>;
  }

  return render(
    <MemoryRouter initialEntries={["/"]}>
      <CommandPalette />
      <Routes>
        <Route path="*" element={<Probe />} />
      </Routes>
    </MemoryRouter>,
  );
}

const open = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.keyboard("{Control>}k{/Control}");
  return screen.findByRole("dialog", { name: /command palette/i });
};

describe("command palette", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is hidden until the shortcut is pressed", async () => {
    const user = userEvent.setup();
    setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await open(user);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes on a second press, so the shortcut toggles", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.keyboard("{Control>}k{/Control}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("navigates to the page you pick", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.click(screen.getByText("Knowledge"));
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/knowledge"));
  });

  it("matches a subsequence, so 'mcps' finds 'MCP servers'", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.type(screen.getByLabelText("Command"), "mcps");
    expect(screen.getByText("MCP servers")).toBeInTheDocument();
  });

  it("filters out what does not match", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.type(screen.getByLabelText("Command"), "knowledge");
    expect(screen.queryByText("Automations")).not.toBeInTheDocument();
  });

  it("finds a page by keyword rather than only by title", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    // "traces" is a keyword on Observability, not part of its label.
    await user.type(screen.getByLabelText("Command"), "traces");
    expect(screen.getByText("Observability")).toBeInTheDocument();
  });

  it("sends an unmatched query to chat instead of dead-ending", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.type(screen.getByLabelText("Command"), "what is 47 times 19");
    expect(screen.getByText(/Ask ORION/)).toBeInTheDocument();

    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(screen.getByTestId("route")).toHaveTextContent("/chat");
      expect(screen.getByTestId("route")).toHaveTextContent("47");
    });
  });

  it("moves the highlight with the arrow keys and runs it on Enter", async () => {
    const user = userEvent.setup();
    const dialog = await (async () => {
      setup();
      return open(user);
    })();

    // Send the keys as separate events and wait for the highlight to settle
    // between them; batching them races React's state update.
    await user.keyboard("{ArrowDown}");
    await waitFor(() =>
      expect(dialog.querySelector(".palette-row.active")?.textContent).toContain("Conversations"),
    );

    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/chat"));
  });

  it("wraps around when arrowing up from the first result", async () => {
    const user = userEvent.setup();
    setup();
    const dialog = await open(user);

    // Assert against whatever is actually last, so adding a command to the
    // palette does not break this test for the wrong reason.
    const rows = () => Array.from(dialog.querySelectorAll(".palette-row"));
    const lastLabel = rows().at(-1)!.textContent;

    await user.keyboard("{ArrowUp}");
    await waitFor(() => {
      const active = dialog.querySelector(".palette-row.active");
      expect(active?.textContent).toBe(lastLabel);
    });
  });

  it("runs the kill switch action and then shows security", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.type(screen.getByLabelText("Command"), "kill");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(api.killSwitch).toHaveBeenCalledWith(true, "command palette");
      expect(screen.getByTestId("route")).toHaveTextContent("/security");
    });
  });

  it("starts from a clean query each time it opens", async () => {
    const user = userEvent.setup();
    setup();
    await open(user);
    await user.type(screen.getByLabelText("Command"), "memory");
    await user.keyboard("{Escape}");
    await open(user);
    expect(screen.getByLabelText("Command")).toHaveValue("");
  });
});
