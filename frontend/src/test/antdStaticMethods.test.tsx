import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { waitFor } from "@testing-library/react";
import { message, Modal } from "antd";

// Regression guard for the React 19 + antd v5 static-method incompatibility.
// antd's static message/Modal/notification rely on the legacy ReactDOM.render,
// removed in React 19, so without @ant-design/v5-patch-for-react-19 they render
// nothing — silently breaking registration feedback, logout confirmation, and
// ~80 other call sites. The patch is imported in src/test/setup.ts to mirror
// main.tsx; remove it and both assertions below fail (verified RED→GREEN).
describe("antd static overlays render on React 19", () => {
  beforeEach(() => message.destroy());
  afterEach(() => {
    message.destroy();
    document.body.querySelectorAll(".ant-message, .ant-modal-root").forEach((n) => n.remove());
  });

  it("message.success renders a toast", async () => {
    message.success("hello-toast-marker");
    await waitFor(() => expect(document.body.textContent).toContain("hello-toast-marker"));
  });

  it("Modal.confirm renders a confirm dialog", async () => {
    Modal.confirm({ title: "confirm-marker", content: "body" });
    await waitFor(() => {
      expect(document.querySelector(".ant-modal-confirm")).not.toBeNull();
      expect(document.body.textContent).toContain("confirm-marker");
    });
  });
});
