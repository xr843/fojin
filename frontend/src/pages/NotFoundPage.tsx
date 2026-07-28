import { useNavigate } from "react-router";
import { Result, Button } from "antd";
import { useTranslation } from "react-i18next";

export default function NotFoundPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <Result
      status="404"
      title={t("notfound.title")}
      subTitle={t("notfound.subtitle")}
      extra={
        <Button type="primary" onClick={() => navigate("/")}>
          {t("notfound.back")}
        </Button>
      }
    />
  );
}
