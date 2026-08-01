import { formatCost, convertHexToRGB, getTimeDifference } from "./utils";

describe("formatCost", () => {
  it("renders zero as $0.00", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(null)).toBe("$0.00");
    expect(formatCost(undefined)).toBe("$0.00");
    expect(formatCost("")).toBe("$0.00");
  });

  it("renders regular amounts with two decimals", () => {
    expect(formatCost(1)).toBe("$1.00");
    expect(formatCost(0.5)).toBe("$0.50");
    expect(formatCost(12.345)).toBe("$12.35");
  });

  it("adds thousands separators", () => {
    expect(formatCost(1234.5)).toBe("$1,234.50");
  });

  it("surfaces sub-cent amounts instead of rounding to $0.00", () => {
    expect(formatCost(0.005)).toBe("$0.0050");
    expect(formatCost(0.000005)).toBe("$0.0000050");
    // never shows a real charge as all zeros
    expect(formatCost(0.000005)).not.toMatch(/^\$0\.0+$/);
  });

  it("caps sub-cent precision at 10 decimals", () => {
    const out = formatCost(1e-12);
    const decimals = out.split(".")[1];
    expect(decimals.length).toBeLessThanOrEqual(10);
  });

  it("uses the absolute value for negative amounts", () => {
    expect(formatCost(-2)).toBe("$2.00");
  });
});

describe("convertHexToRGB", () => {
  it("converts 6-digit hex", () => {
    expect(convertHexToRGB("#ff0000")).toBe("255,0,0");
    expect(convertHexToRGB("#00ff7f")).toBe("0,255,127");
  });

  it("converts 3-digit shorthand hex", () => {
    expect(convertHexToRGB("#fff")).toBe("255,255,255");
    expect(convertHexToRGB("#f00")).toBe("255,0,0");
  });

  it("extracts the triplet from an rgba() string", () => {
    expect(convertHexToRGB("rgba(10, 20, 30, 0.5)")).toBe("10, 20, 30");
  });

  it("returns undefined for invalid input", () => {
    expect(convertHexToRGB("not-a-color")).toBeUndefined();
  });
});

describe("getTimeDifference", () => {
  afterEach(() => jest.useRealTimers());

  const at = (secondsAgo) => new Date(Date.now() - secondsAgo * 1000);

  it("formats seconds, minutes, days and months", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-01T12:00:00Z"));
    expect(getTimeDifference(at(30))).toBe("30 sec");
    expect(getTimeDifference(at(120))).toBe("2 min");
    expect(getTimeDifference(at(7200))).toBe("2 h");
    expect(getTimeDifference(at(86400 * 3))).toBe("3 d");
    expect(getTimeDifference(at(86400 * 60))).toBe("2 mon");
  });
});
