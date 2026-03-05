import { Component, type ErrorInfo, type ReactNode } from "react";
import { Result, Button, Space } from "antd";

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
          title="页面渲染出错"
          subTitle="抱歉，页面遇到了意外错误。请尝试刷新页面。"
          extra={
            <Space>
              <Button
                type="primary"
                onClick={() => {
                  this.setState({ hasError: false });
                  window.location.reload();
                }}
              >
                刷新页面
              </Button>
              <Button
                onClick={() => {
                  this.setState({ hasError: false });
                  window.location.href = "/";
                }}
              >
                返回首页
              </Button>
            </Space>
          }
        />
      );
    }
    return this.props.children;
  }
}
