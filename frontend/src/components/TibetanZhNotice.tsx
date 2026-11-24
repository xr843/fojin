import { Alert } from "antd";
import { useTranslation } from "react-i18next";
import { TIBETAN_ZH_REPO } from "../api/tibetanZh";

/** 藏译汉稿页顶提示：AI 译稿、未经专家审定、以 GitHub 源项目为准。列表页与阅读页共用，不要删。 */
export default function TibetanZhNotice({ rv }: { rv?: string }) {
  const { t } = useTranslation();
  return (
    <Alert
      className="tz-notice"
      type="warning"
      showIcon
      message={t("tibetanZh.notice_title")}
      description={
        <>
          {rv && (
            <div className="tz-notice-rv">
              {t("tibetanZh.review_status")}
              {rv}
            </div>
          )}
          <div>
            {t("tibetanZh.notice_source")}
            <a href={TIBETAN_ZH_REPO} target="_blank" rel="noopener noreferrer">
              github.com/xr843/tibetan-canon-zh
            </a>
          </div>
        </>
      }
    />
  );
}
