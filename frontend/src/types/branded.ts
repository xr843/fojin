// 品牌化类型（Branded Types）：防止不同实体的 ID 混用
// 这是编译期检查，运行时零开销。渐进式引入的第一步，只建立类型基础。

declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

/** 经文 ID */
export type TextId = Brand<number, "TextId">;
/** 数据源 ID */
export type SourceId = Brand<number, "SourceId">;
/** 聊天会话 ID */
export type ChatSessionId = Brand<number, "ChatSessionId">;
/** 用户 ID */
export type UserId = Brand<number, "UserId">;
/** 词典条目 ID */
export type DictEntryId = Brand<number, "DictEntryId">;
/** 知识图谱实体 ID */
export type KGEntityId = Brand<number, "KGEntityId">;
/** 标注 ID */
export type AnnotationId = Brand<number, "AnnotationId">;
/** 书签 ID */
export type BookmarkId = Brand<number, "BookmarkId">;
/** 通知 ID */
export type NotificationId = Brand<number, "NotificationId">;
/** IIIF Manifest ID */
export type IIIFManifestId = Brand<number, "IIIFManifestId">;
