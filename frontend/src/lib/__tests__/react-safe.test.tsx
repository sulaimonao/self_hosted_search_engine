import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useEvent, useSafeState, useStableMemo } from "../react-safe";

describe("react-safe helpers", () => {
  it("useSafeState skips redundant updates", () => {
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      const [value, setValue] = useSafeState(0);
      return { value, setValue };
    });

    expect(result.current.value).toBe(0);
    expect(renders).toBe(1);

    act(() => {
      result.current.setValue(0);
    });
    expect(result.current.value).toBe(0);
    expect(renders).toBe(1);

    act(() => {
      result.current.setValue((previous) => previous + 1);
    });
    expect(result.current.value).toBe(1);
    expect(renders).toBe(2);
  });

  it("useStableMemo reuses objects when shallowly equal", () => {
    const { result, rerender } = renderHook(
      ({ flag }: { flag: boolean }) =>
        useStableMemo(
          () => ({
            flag,
            constant: "value",
          }),
          [flag],
        ),
      { initialProps: { flag: true } },
    );

    const first = result.current;
    rerender({ flag: true });
    expect(result.current).toBe(first);

    rerender({ flag: false });
    expect(result.current).not.toBe(first);
  });

  it("useEvent preserves callback identity and updates implementation", () => {
    const handlerA = vi.fn();
    const handlerB = vi.fn();

    const { result, rerender } = renderHook(({ handler }: { handler: () => void }) => useEvent(handler), {
      initialProps: { handler: handlerA },
    });

    const stable = result.current;
    expect(typeof stable).toBe("function");

    stable();
    expect(handlerA).toHaveBeenCalledTimes(1);

    rerender({ handler: handlerB });
    expect(result.current).toBe(stable);

    result.current();
    expect(handlerB).toHaveBeenCalledTimes(1);
    expect(handlerA).toHaveBeenCalledTimes(1);
  });
});
