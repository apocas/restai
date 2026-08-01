import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SimpleCard from "./SimpleCard";
import MatxLoading from "./MatxLoading";
import NotFound from "app/views/sessions/NotFound";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

describe("SimpleCard", () => {
  it("renders title, optional subtitle, and children", () => {
    render(
      <SimpleCard title="My Card" subtitle="sub here">
        <span>body</span>
      </SimpleCard>
    );
    expect(screen.getByText("My Card")).toBeInTheDocument();
    expect(screen.getByText("sub here")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("renders without a subtitle", () => {
    render(<SimpleCard title="Solo" />);
    expect(screen.getByText("Solo")).toBeInTheDocument();
  });
});

describe("MatxLoading", () => {
  it("shows the logo and a progress spinner", () => {
    render(<MatxLoading />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });
});

describe("NotFound", () => {
  it("navigates back when Go Back is clicked", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    await user.click(screen.getByRole("button", { name: /go back/i }));
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });
});
