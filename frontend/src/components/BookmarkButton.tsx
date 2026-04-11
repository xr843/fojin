import { Button, message } from "antd";
import { HeartOutlined, HeartFilled } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../stores/authStore";
import { addBookmark, removeBookmark, checkBookmark } from "../api/client";

interface BookmarkButtonProps {
  textId: number;
  size?: "small" | "middle" | "large";
  solid?: boolean;
}

export default function BookmarkButton({ textId, size, solid }: BookmarkButtonProps) {
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
      message.success(bookmarked ? "已取消收藏" : "已收藏");
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || "操作失败");
    },
  });

  if (!user) return null;

  if (solid) {
    return (
      <Button
        type="primary"
        size={size}
        icon={bookmarked ? <HeartFilled /> : <HeartOutlined />}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
        style={{ background: "#7c3aed", borderColor: "#7c3aed", color: "#fff" }}
      >
        {bookmarked ? "已收藏" : "收藏"}
      </Button>
    );
  }

  return (
    <Button
      type="text"
      size={size}
      icon={bookmarked ? <HeartFilled style={{ color: "#ff4d4f" }} /> : <HeartOutlined />}
      loading={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {bookmarked ? "已收藏" : "收藏"}
    </Button>
  );
}
