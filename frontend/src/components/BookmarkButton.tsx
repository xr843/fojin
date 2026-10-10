import { Button, message } from "antd";
import { HeartOutlined, HeartFilled } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useAuthStore } from "../stores/authStore";
import { addBookmark, removeBookmark, checkBookmark } from "../api/client";

interface BookmarkButtonProps {
  textId: number;
  size?: "small" | "middle" | "large";
  /** 默认文字按钮（搜索结果卡里与「查看详情」并排时要轻）；详情页的次级按钮组用 "default" 统一描边。 */
  type?: "text" | "default";
}

interface ErrorResponse {
  detail?: unknown;
}

function getErrorDetail(err: unknown): string | undefined {
  if (!axios.isAxiosError<ErrorResponse>(err)) return undefined;
  const detail = err.response?.data?.detail;
  return typeof detail === "string" ? detail : undefined;
}

export default function BookmarkButton({ textId, size, type = "text" }: BookmarkButtonProps) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();

  const { data: bookmarked = false } = useQuery({
    queryKey: ["bookmark", textId],
    queryFn: () => checkBookmark(textId),
    enabled: !!user,
  });

  const mutation = useMutation({
    mutationFn: async () => { if (bookmarked) { await removeBookmark(textId); } else { await addBookmark(textId); } },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bookmark", textId] });
      queryClient.invalidateQueries({ queryKey: ["bookmarks"] });
      message.success(bookmarked ? t("reader.bookmark.removed") : t("reader.bookmark.added"));
    },
    onError: (err: unknown) => {
      message.error(getErrorDetail(err) || t("reader.bookmark.failed"));
    },
  });

  if (!user) return null;

  return (
    <Button
      type={type}
      size={size}
      icon={bookmarked ? <HeartFilled style={{ color: "#ff4d4f" }} /> : <HeartOutlined />}
      loading={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {bookmarked ? t("reader.bookmark.added") : t("reader.bookmark.add")}
    </Button>
  );
}
