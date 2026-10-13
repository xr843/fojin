import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "antd";
import { CloseOutlined, TeamOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { dismissCommunityInvite, getCommunityInvite, getCommunityInviteQr } from "../api/client";
import "../styles/community-invite.css";

/**
 * fojin研读交流群的站内邀请（只对服务器名单里的已登录用户出现）。
 *
 * 是否邀请、二维码图片都由后端判定并下发（backend/app/services/community_invite.py），
 * 前端包里没有名单也没有二维码。二维码带登录凭证取回后转成 data URL 显示，
 * 不落浏览器缓存、不进 react-query 的长期缓存。
 */

type Device = "wechat" | "mobile" | "desktop";

function detectDevice(): Device {
  if (typeof navigator === "undefined") return "desktop";
  const ua = navigator.userAgent;
  if (/MicroMessenger/i.test(ua)) return "wechat";
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(ua)) return "mobile";
  return "desktop";
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

// 缓存键必须带用户 id：同一台设备上 A 退出、B 登录时，B 不能沿用 A 的「受邀」结果
// （与 expired-token 那次「常量 queryKey 缓存了别人的配额」是同一类坑）。
const inviteKey = (userId: number | null) => ["communityInvite", userId] as const;

export default function CommunityInvite({ userId }: { userId: number | null }) {
  const enabled = userId != null;
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [device] = useState(detectDevice);

  const { data } = useQuery({
    queryKey: inviteKey(userId),
    queryFn: getCommunityInvite,
    enabled,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  const invited = enabled && data?.invited === true;

  const qr = useQuery({
    queryKey: ["communityInviteQr", userId],
    queryFn: async () => blobToDataUrl(await getCommunityInviteQr()),
    enabled: invited && expanded,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  const dismiss = useMutation({
    mutationFn: dismissCommunityInvite,
    onSettled: () => qc.setQueryData(inviteKey(userId), { invited: false }),
  });

  useEffect(() => {
    if (invited && typeof umami !== "undefined") umami.track("community_invite_shown");
  }, [invited]);

  if (!invited) return null;

  const hint =
    device === "wechat"
      ? t("chat.community_invite.hint_wechat")
      : device === "mobile"
        ? t("chat.community_invite.hint_mobile")
        : t("chat.community_invite.hint_desktop");

  return (
    <section className="community-invite" aria-label={t("chat.community_invite.title")}>
      <div className="community-invite-head">
        <TeamOutlined className="community-invite-icon" aria-hidden />
        <div className="community-invite-text">
          <div className="community-invite-title">{t("chat.community_invite.title")}</div>
          <div className="community-invite-body">{t("chat.community_invite.body")}</div>
        </div>
        <button
          type="button"
          className="community-invite-close"
          aria-label={t("chat.community_invite.close")}
          onClick={() => {
            if (typeof umami !== "undefined") umami.track("community_invite_dismiss");
            dismiss.mutate();
          }}
        >
          <CloseOutlined />
        </button>
      </div>

      {!expanded ? (
        <div className="community-invite-actions">
          <Button
            type="primary"
            size="small"
            onClick={() => {
              if (typeof umami !== "undefined") umami.track("community_invite_qr");
              setExpanded(true);
            }}
          >
            {t("chat.community_invite.add")}
          </Button>
          <Button
            type="text"
            size="small"
            onClick={() => {
              if (typeof umami !== "undefined") umami.track("community_invite_dismiss");
              dismiss.mutate();
            }}
          >
            {t("chat.community_invite.decline")}
          </Button>
        </div>
      ) : (
        <div className="community-invite-qr">
          {qr.data ? (
            <img src={qr.data} alt={t("chat.community_invite.qr_alt")} className="community-invite-qr-img" />
          ) : qr.isError ? (
            <div className="community-invite-qr-msg">{t("chat.community_invite.qr_error")}</div>
          ) : (
            <div className="community-invite-qr-msg" aria-busy="true">…</div>
          )}
          <ul className="community-invite-steps">
            <li>{hint}</li>
            <li>{t("chat.community_invite.note")}</li>
            <li>{t("chat.community_invite.friend")}</li>
          </ul>
          <div className="community-invite-qr-foot">
            <Button type="text" size="small" onClick={() => setExpanded(false)}>
              {t("chat.community_invite.collapse")}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
