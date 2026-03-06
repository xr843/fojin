import { Component, type ErrorInfo, type ReactNode } from "react";
import { Result, Button } from "antd";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Route-level error boundary. Unlike the top-level ErrorBoundary,
 * this resets on retry without a full page reload — only the wrapped
 * route re-mounts, keeping the rest of the app intact.
 */
export default class RouteErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RouteErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="warning"
          title="此页面加载出错"
          subTitle="其他页面不受影响，您可以尝试重新加载此页面。"
          extra={
            <Button
              type="primary"
              onClick={() => this.setState({ hasError: false })}
            >
              重试
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
