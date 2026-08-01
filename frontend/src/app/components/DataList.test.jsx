import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DataList from "./DataList";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k, opts) => (opts && opts.count !== undefined ? `${k}:${opts.count}` : k),
  }),
}));

const columns = [
  { key: "name", label: "Name", sortable: true },
  { key: "meta.level", label: "Level" },
  { key: "size", label: "Size", sortable: true },
];

const data = [
  { id: 1, name: "banana", size: 3, meta: { level: "low" } },
  { id: 2, name: "apple", size: 9, meta: { level: "high" } },
  { id: 3, name: "cherry", size: 1, meta: { level: "low" } },
];

const bodyRows = () => {
  const rows = screen.getAllByRole("row");
  // First row is the header.
  return rows.slice(1);
};

describe("DataList", () => {
  it("renders title, subtitle, headers, plain and nested cell values", () => {
    render(<DataList title="Fruits" subtitle="all of them" data={data} columns={columns} />);
    expect(screen.getByText("Fruits")).toBeInTheDocument();
    expect(screen.getByText("all of them")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("banana")).toBeInTheDocument();
    expect(screen.getAllByText("low")).toHaveLength(2); // nested meta.level
    expect(bodyRows()).toHaveLength(3);
  });

  it("shows the default empty message with no data", () => {
    render(<DataList data={[]} columns={columns} />);
    expect(screen.getByText("dataList.noResults")).toBeInTheDocument();
  });

  it("shows a custom emptyState with an action button", async () => {
    const user = userEvent.setup();
    const onAction = jest.fn();
    render(
      <DataList
        data={[]}
        columns={columns}
        emptyState={{ title: "Nothing here", message: "Add one", actionLabel: "Create", onAction }}
      />
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Add one")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onAction).toHaveBeenCalled();
  });

  it("filters rows by search and can clear back", async () => {
    const user = userEvent.setup();
    render(<DataList data={data} columns={columns} searchKeys={["name"]} />);
    const input = screen.getByPlaceholderText("dataList.search");

    await user.type(input, "app");
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText("apple")).toBeInTheDocument();
    expect(screen.getByText("common.resultCount:1")).toBeInTheDocument();

    await user.click(screen.getByLabelText("dataList.clearSearch"));
    expect(bodyRows()).toHaveLength(3);
  });

  it("shows the no-matches empty state when a search finds nothing", async () => {
    const user = userEvent.setup();
    render(<DataList data={data} columns={columns} searchKeys={["name"]} />);
    await user.type(screen.getByPlaceholderText("dataList.search"), "zzz");
    expect(screen.getByText("dataList.noMatches")).toBeInTheDocument();
  });

  it("sorts by a sortable column and toggles direction on second click", async () => {
    const user = userEvent.setup();
    render(<DataList data={data} columns={columns} />);
    await user.click(screen.getByText("Name"));
    let rows = bodyRows();
    expect(within(rows[0]).getByText("apple")).toBeInTheDocument();

    await user.click(screen.getByText("Name"));
    rows = bodyRows();
    expect(within(rows[0]).getByText("cherry")).toBeInTheDocument();
  });

  it("sorts numerically via defaultSort", () => {
    render(
      <DataList data={data} columns={columns} defaultSort={{ key: "size", direction: "desc" }} />
    );
    const rows = bodyRows();
    expect(within(rows[0]).getByText("apple")).toBeInTheDocument(); // size 9
    expect(within(rows[2]).getByText("cherry")).toBeInTheDocument(); // size 1
  });

  it("invokes onRowClick with the row, but not for clicks on inner buttons", async () => {
    const user = userEvent.setup();
    const onRowClick = jest.fn();
    const action = jest.fn();
    render(
      <DataList
        data={data}
        columns={columns}
        onRowClick={onRowClick}
        actions={(row) => (
          <button onClick={() => action(row.id)}>act-{row.id}</button>
        )}
      />
    );

    await user.click(screen.getByText("banana"));
    expect(onRowClick).toHaveBeenCalledWith(data[0]);

    onRowClick.mockClear();
    await user.click(screen.getByRole("button", { name: "act-2" }));
    expect(action).toHaveBeenCalledWith(2);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("paginates when rows exceed the page size", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 12 }, (_, i) => ({ id: i, name: `row-${i}`, size: i }));
    render(<DataList data={many} columns={columns} pageSize={10} />);

    expect(bodyRows()).toHaveLength(10);
    await user.click(screen.getByRole("button", { name: /next page/i }));
    expect(bodyRows()).toHaveLength(2);
    expect(screen.getByText("row-11")).toBeInTheDocument();
  });

  it("selects rows and runs a bulk action over them, then clears the selection", async () => {
    const user = userEvent.setup();
    const onBulk = jest.fn().mockResolvedValue();
    render(
      <DataList
        data={data}
        columns={columns}
        bulkActions={[{ label: "Zap", onClick: onBulk }]}
      />
    );

    await user.click(screen.getByLabelText("select row 1"));
    await user.click(screen.getByLabelText("select row 3"));
    expect(screen.getByText("dataList.selected:2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Zap" }));
    expect(onBulk).toHaveBeenCalledWith([data[0], data[2]]);
    // Selection cleared after the action resolves.
    expect(await screen.findByLabelText("select row 1")).not.toBeChecked();
    expect(screen.queryByText("dataList.selected:2")).not.toBeInTheDocument();
  });

  it("select-all checkbox toggles every row on the page", () => {
    render(
      <DataList data={data} columns={columns} bulkActions={[{ label: "X", onClick: jest.fn() }]} />
    );
    fireEvent.click(screen.getByLabelText("select all on page"));
    expect(screen.getByText("dataList.selected:3")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("select all on page"));
    expect(screen.queryByText(/dataList\.selected/)).not.toBeInTheDocument();
  });
});
