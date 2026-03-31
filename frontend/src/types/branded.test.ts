import { describe, it, expect } from "vitest";
import type { TextId, SourceId, ChatSessionId, UserId } from "./branded";

/**
 * Branded Types 编译期类型测试。
 * 验证品牌化类型在类型系统层面的安全性和向后兼容性。
 * 这些测试主要在编译期起作用，运行时仅做基本断言。
 */

describe("Branded Types 类型安全", () => {
  it("TextId 可以用于需要 number 的地方（向后兼容）", () => {
    const textId = 42 as TextId;

    // branded number 可以赋值给 number（向上兼容）
    const num: number = textId;
    expect(num).toBe(42);

    // 可以传入需要 number 参数的函数
    function acceptNumber(n: number): number {
      return n;
    }
    expect(acceptNumber(textId)).toBe(42);
  });

  it("不同品牌类型不能互相赋值（类型安全）", () => {
    const textId = 1 as TextId;
    const sourceId = 2 as SourceId;

    // @ts-expect-error TextId 不能赋值给 SourceId
    const _wrongSource: SourceId = textId;

    // @ts-expect-error SourceId 不能赋值给 TextId
    const _wrongText: TextId = sourceId;

    // @ts-expect-error ChatSessionId 不能赋值给 UserId
    const _wrongUser: UserId = 3 as ChatSessionId;

    // 运行时值本身是 number，断言确保测试不被优化掉
    expect(textId).toBe(1);
    expect(sourceId).toBe(2);
  });

  it("branded number 支持比较运算", () => {
    const a = 10 as TextId;
    const b = 20 as TextId;

    expect(a < b).toBe(true);
    expect(a > b).toBe(false);
    expect(a === a).toBe(true);
    expect(a !== b).toBe(true);
  });

  it("branded number 支持算术运算", () => {
    const id = 5 as TextId;

    // 算术运算结果是 number（不再是 TextId），这是预期行为
    const result = id + 1;
    expect(result).toBe(6);

    const doubled = id * 2;
    expect(doubled).toBe(10);
  });

  it("普通 number 不能直接赋值给 branded type", () => {
    const plainNumber = 42;

    // @ts-expect-error 普通 number 不能赋值给 TextId
    const _id: TextId = plainNumber;

    // 需要显式 as 断言才能创建 branded type
    const validId = plainNumber as TextId;
    expect(validId).toBe(42);
  });
});
