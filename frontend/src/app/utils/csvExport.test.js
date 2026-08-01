import { toCsv, downloadCsv } from "./csvExport";

describe("toCsv", () => {
  const rows = [
    { name: "alpha", count: 3 },
    { name: "beta", count: 7 },
  ];

  it("builds a header line plus one line per row, CRLF-joined", () => {
    const csv = toCsv(rows, [{ key: "name" }, { key: "count" }]);
    expect(csv).toBe("name,count\r\nalpha,3\r\nbeta,7");
  });

  it("uses header labels when given, falling back to key", () => {
    const csv = toCsv([], [{ key: "a", header: "Column A" }, { key: "b" }]);
    expect(csv).toBe("Column A,b");
  });

  it("prefers the get() accessor over row[key]", () => {
    const csv = toCsv(rows, [{ key: "name", get: (r) => r.name.toUpperCase() }]);
    expect(csv).toBe("name\r\nALPHA\r\nBETA");
  });

  it("escapes commas, quotes and newlines per RFC 4180", () => {
    const tricky = [{ v: 'say "hi", ok?\nnew line' }];
    const csv = toCsv(tricky, [{ key: "v" }]);
    expect(csv).toBe('v\r\n"say ""hi"", ok?\nnew line"');
  });

  it("renders null/undefined as empty and objects as JSON", () => {
    const csv = toCsv([{ a: null, b: { x: 1 } }], [{ key: "a" }, { key: "b" }]);
    expect(csv).toBe('a,b\r\n,"{""x"":1}"');
  });
});

describe("downloadCsv", () => {
  afterEach(() => jest.useRealTimers());

  it("creates a temporary anchor with a .csv filename and clicks it", () => {
    jest.useFakeTimers();
    const clicks = [];
    const origCreateObjectURL = URL.createObjectURL;
    const origRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = jest.fn(() => "blob:fake");
    URL.revokeObjectURL = jest.fn();
    const clickSpy = jest
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function () {
        clicks.push({ href: this.href, download: this.download });
      });

    try {
      downloadCsv("report", "a,b\r\n1,2");
      expect(clicks).toHaveLength(1);
      expect(clicks[0].download).toBe("report.csv");

      downloadCsv("already.csv", "x");
      expect(clicks[1].download).toBe("already.csv");

      // Flush the deferred revokeObjectURL while the mock is still installed.
      jest.runOnlyPendingTimers();
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake");
    } finally {
      clickSpy.mockRestore();
      URL.createObjectURL = origCreateObjectURL;
      URL.revokeObjectURL = origRevokeObjectURL;
    }
  });
});
