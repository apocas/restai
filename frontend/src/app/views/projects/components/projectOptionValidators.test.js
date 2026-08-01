import { clientValidators, makeErrorFor } from "./projectOptionValidators";

describe("clientValidators", () => {
  it.each(["", null, undefined])("treats %p as valid (unset) everywhere", (v) => {
    for (const validator of Object.values(clientValidators)) {
      expect(validator(v)).toBe("");
    }
  });

  it("bounds rate_limit to 1..10000", () => {
    expect(clientValidators.rate_limit(1)).toBe("");
    expect(clientValidators.rate_limit(10000)).toBe("");
    expect(clientValidators.rate_limit(0)).not.toBe("");
    expect(clientValidators.rate_limit(10001)).not.toBe("");
    expect(clientValidators.rate_limit("abc")).not.toBe("");
  });

  it("requires k >= 1", () => {
    expect(clientValidators.k(1)).toBe("");
    expect(clientValidators.k(50)).toBe("");
    expect(clientValidators.k(0)).not.toBe("");
    expect(clientValidators.k(-1)).not.toBe("");
  });

  it("bounds score to 0..1", () => {
    expect(clientValidators.score(0)).toBe("");
    expect(clientValidators.score(0.5)).toBe("");
    expect(clientValidators.score(1)).toBe("");
    expect(clientValidators.score(1.5)).not.toBe("");
    expect(clientValidators.score(-0.1)).not.toBe("");
  });

  it("bounds memory_bank_max_tokens to 200..10000", () => {
    expect(clientValidators.memory_bank_max_tokens(200)).toBe("");
    expect(clientValidators.memory_bank_max_tokens(10000)).toBe("");
    expect(clientValidators.memory_bank_max_tokens(199)).not.toBe("");
    expect(clientValidators.memory_bank_max_tokens(10001)).not.toBe("");
  });
});

describe("makeErrorFor", () => {
  it("returns the server error when present, verbatim", () => {
    const errorFor = makeErrorFor({ rate_limit: "server says no" }, { options: { rate_limit: 5 } });
    expect(errorFor("rate_limit")).toBe("server says no");
  });

  it("accepts options.-prefixed server keys (nested Pydantic locs)", () => {
    const errorFor = makeErrorFor({ "options.k": "k is broken" }, { options: { k: 5 } });
    expect(errorFor("k")).toBe("k is broken");
  });

  it("falls back to the client validator when no server error", () => {
    const errorFor = makeErrorFor({}, { options: { rate_limit: 0 } });
    expect(errorFor("rate_limit")).toMatch(/between 1 and 10000/);
  });

  it("returns empty for unknown fields and valid values", () => {
    const errorFor = makeErrorFor({}, { options: { rate_limit: 10 } });
    expect(errorFor("rate_limit")).toBe("");
    expect(errorFor("no_such_field")).toBe("");
  });

  it("survives null fieldErrors and missing state", () => {
    const errorFor = makeErrorFor(null, undefined);
    expect(errorFor("rate_limit")).toBe("");
  });
});
