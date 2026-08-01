import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectEditSecurity from "./ProjectEditSecurity";

jest.setTimeout(20000);

jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k) => k }) }));

const PROJECTS = [
  { id: 3, name: "self", human_name: "Myself" },
  { id: 12, name: "guard-in", human_name: "Input Guard" },
  { id: 13, name: "guard-out" }, // no human_name → labeled by name
];

const baseState = {
  id: 3,
  guard: "",
  censorship: "",
  options: {},
};

const setup = (stateOverrides = {}, props = {}) => {
  const state = { ...baseState, ...stateOverrides };
  const setState = jest.fn();
  const handleChange = jest.fn();
  const clearFieldError = jest.fn();
  const utils = render(
    <ProjectEditSecurity
      state={state}
      setState={setState}
      handleChange={handleChange}
      projects={PROJECTS}
      project={{ id: 3, name: "self", type: "agent" }}
      clearFieldError={clearFieldError}
      {...props}
    />
  );
  return { state, setState, handleChange, clearFieldError, ...utils };
};

describe("ProjectEditSecurity", () => {
  it("guard pickers exclude the project itself from the options", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByLabelText("projects.edit.security.inputGuard"));
    const listbox = await screen.findByRole("listbox");
    const options = within(listbox).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Input Guard", "guard-out"]);
    expect(options).not.toContain("Myself");
  });

  it("selecting an input guard stores the guard project ID as a string", async () => {
    const user = userEvent.setup();
    const { setState, state } = setup();

    await user.click(screen.getByLabelText("projects.edit.security.inputGuard"));
    await user.click(await screen.findByRole("option", { name: "Input Guard" }));

    expect(setState).toHaveBeenCalledWith({ ...state, guard: "12" });
  });

  it("labels the selected input guard by name when state.guard holds an id", () => {
    setup({ guard: "12" });
    expect(screen.getByLabelText("projects.edit.security.inputGuard")).toHaveValue("Input Guard");
  });

  it("selecting an output guard stores the id under options.guard_output; clearing stores null", async () => {
    const user = userEvent.setup();
    const { setState, state } = setup({ options: { guard_output: "13" } });

    const outputPicker = screen.getByLabelText("projects.edit.security.outputGuard");
    expect(outputPicker).toHaveValue("guard-out");

    await user.click(outputPicker);
    await user.click(await screen.findByRole("option", { name: "Input Guard" }));
    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: { ...state.options, guard_output: "12" },
    });

    setState.mockClear();
    // only the output guard has a value → single Clear indicator
    await user.click(screen.getByLabelText("Clear"));
    expect(setState).toHaveBeenLastCalledWith({
      ...state,
      options: { ...state.options, guard_output: null },
    });
  });

  it("guard mode select defaults to block and writes options.guard_mode on change", async () => {
    const user = userEvent.setup();
    const { setState, state } = setup();

    const select = screen.getByLabelText("projects.edit.security.guardMode");
    expect(select).toHaveTextContent("Block");
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: "Warn" }));
    expect(setState).toHaveBeenCalledWith({
      ...state,
      options: { ...state.options, guard_mode: "warn" },
    });
  });

  it("censorship + rate limit fields are wired through handleChange, clearing field errors", async () => {
    const user = userEvent.setup();
    const { handleChange, clearFieldError } = setup({ options: { rate_limit: 5 } });

    await user.type(screen.getByLabelText("projects.edit.general.censorship"), "x");
    expect(handleChange).toHaveBeenCalled();
    expect(
      handleChange.mock.calls.some(([e]) => e.target.name === "censorship")
    ).toBe(true);

    handleChange.mockClear();
    await user.type(screen.getByLabelText("projects.edit.security.rateLimit"), "0");
    expect(clearFieldError).toHaveBeenCalledWith("rate_limit");
    expect(handleChange.mock.calls.some(([e]) => e.target.name === "rate_limit")).toBe(true);
  });

  it("shows a server field error on the rate limit field", () => {
    setup({}, { fieldErrors: { "options.rate_limit": "must be <= 10000" } });
    expect(screen.getByText("must be <= 10000")).toBeInTheDocument();
  });
});
