import { Component, type ErrorInfo, type ReactNode } from "react";
import { Result, Button } from "antd";
import i18n from "../i18n";

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
          title={i18n.t("error.route.title")}
          subTitle={i18n.t("error.route.subtitle")}
          extra={
            <Button
              type="primary"
              onClick={() => this.setState({ hasError: false })}
            >
              {i18n.t("error.route.retry")}
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
