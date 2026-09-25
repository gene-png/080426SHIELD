const ON = process.env.E2E_PERF === "1";
test("x", () => { test.skip(!ON, "set E2E_PERF=1"); });
