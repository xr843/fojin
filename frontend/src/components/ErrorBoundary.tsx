import { Component, type ErrorInfo, type ReactNode } from "react";
import { Result, Button, Space } from "antd";
import i18n from "../i18n";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title={i18n.t("error.boundary.title")}
          subTitle={i18n.t("error.boundary.subtitle")}
          extra={
            <Space>
              <Button
                type="primary"
                onClick={() => {
                  this.setState({ hasError: false });
                  window.location.reload();
                }}
              >
                {i18n.t("error.boundary.reload")}
              </Button>
              <Button
                onClick={() => {
                  this.setState({ hasError: false });
                  window.location.href = "/";
                }}
              >
                {i18n.t("error.boundary.home")}
              </Button>
            </Space>
          }
        />
      );
    }
    return this.props.children;
  }
}
