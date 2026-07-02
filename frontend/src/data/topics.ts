import topicsEn from "../content/topicLocales/en.json";
import topicsZhHant from "../content/topicLocales/zh-Hant.json";
import topicsZh from "../content/topicLocales/zh.json";

export interface TopicText {
  title: string;
  textId?: number;
  description: string;
}

export interface Topic {
  id: string;
  name: string;
  icon: string;
  description: string;
  searchQuery: string;
  texts: TopicText[];
}

interface TopicBase {
  id: Topic["id"];
  icon: string;
}

interface TopicLocaleContent {
  name: string;
  description: string;
  searchQuery: string;
  texts: TopicText[];
}

type TopicLocaleMap = Record<string, TopicLocaleContent>;
type TopicLocaleKey = "en" | "zh" | "zh-Hant";

const TOPIC_BASE: TopicBase[] = [
  { id: "prajna", icon: "\u{1F4DC}" },
  { id: "pureland", icon: "\u{1FAB7}" },
  { id: "lotus", icon: "\u{1F338}" },
  { id: "chan", icon: "\u{1F9D8}" },
  { id: "vinaya", icon: "\u{1F4CF}" },
  { id: "agama", icon: "\u{1F4D6}" },
  { id: "yogacara", icon: "\u{1F50D}" },
  { id: "avatamsaka", icon: "\u2728" },
];

const TOPIC_LOCALES: Record<TopicLocaleKey, TopicLocaleMap> = {
  en: topicsEn,
  zh: topicsZh,
  "zh-Hant": topicsZhHant,
};

function normalizeTopicLocale(language: string): TopicLocaleKey {
  if (language.startsWith("en")) return "en";
  if (
    language.startsWith("zh-Hant") ||
    language.startsWith("zh-TW") ||
    language.startsWith("zh-HK")
  ) {
    return "zh-Hant";
  }
  return "zh";
}

export function getLocalizedTopics(language: string): Topic[] {
  const locale = normalizeTopicLocale(language);
  const content = TOPIC_LOCALES[locale];
  const fallback = TOPIC_LOCALES.zh;

  return TOPIC_BASE.map((topic) => {
    const localized = content[topic.id] ?? fallback[topic.id];
    return {
      id: topic.id,
      icon: topic.icon,
      ...localized,
    };
  });
}

export const TOPICS: Topic[] = getLocalizedTopics("zh");
