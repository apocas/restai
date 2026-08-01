import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MenuItem } from "@mui/material";
import MatxMenu from "./MatxMenu";
import SettingsProvider from "app/contexts/SettingsContext";

const renderMenu = (props = {}) =>
  render(
    <SettingsProvider>
      <MatxMenu menuButton={<span>open me</span>} {...props}>
        <MenuItem>First</MenuItem>
        <MenuItem>Second</MenuItem>
      </MatxMenu>
    </SettingsProvider>
  );

describe("MatxMenu", () => {
  it("keeps the menu closed until the anchor is clicked", () => {
    renderMenu();
    expect(screen.getByText("open me")).toBeInTheDocument();
    expect(screen.queryByText("First")).not.toBeInTheDocument();
  });

  it("opens on anchor click, showing all children", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByText("open me"));
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  it("closes after clicking an item by default", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByText("open me"));
    await user.click(screen.getByText("First"));
    await waitFor(() => {
      expect(screen.queryByText("First")).not.toBeInTheDocument();
    });
  });

  it("stays open on item click when shouldCloseOnItemClick is false", async () => {
    const user = userEvent.setup();
    renderMenu({ shouldCloseOnItemClick: false });
    await user.click(screen.getByText("open me"));
    await user.click(screen.getByText("First"));
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  it("closes on escape", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByText("open me"));
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByText("First")).not.toBeInTheDocument();
    });
  });
});
