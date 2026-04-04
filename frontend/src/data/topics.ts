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
  texts: TopicText[];
}

export const TOPICS: Topic[] = [
  {
    id: "prajna",
    name: "般若系经典",
    icon: "\u{1F4DC}",
    description: "以空性智慧为核心的经典群，从《心经》260字的精要到《大般若经》600卷的浩瀚。",
    texts: [
      { title: "般若波罗蜜多心经", description: "最简短的般若经典，260字概括般若思想精髓" },
      { title: "金刚般若波罗蜜经", description: "以金刚喻般若智慧，禅宗重要依据经典" },
      { title: "摩诃般若波罗蜜经", description: "鸠摩罗什译，般若系重要经典" },
      { title: "大般若波罗蜜多经", description: "玄奘译，600卷，般若类经典集大成" },
    ],
  },
  {
    id: "pureland",
    name: "净土五经",
    icon: "\u{1FAB7}",
    description: "净土宗核心经典，描述西方极乐世界及往生法门。",
    texts: [
      { title: "佛说阿弥陀经", description: "净土三经之一，最广为流传的净土经典" },
      { title: "佛说无量寿经", description: "详述阿弥陀佛四十八愿" },
      { title: "佛说观无量寿佛经", description: "十六观法与九品往生" },
      { title: "大势至菩萨念佛圆通章", description: "出自《楞严经》，念佛法门精要" },
      { title: "普贤菩萨行愿品", description: "出自《华严经》，十大愿王导归极乐" },
    ],
  },
  {
    id: "lotus",
    name: "法华系经典",
    icon: "\u{1F338}",
    description: "天台宗根本经典，开权显实，会三归一。",
    texts: [
      { title: "妙法莲华经", description: "鸠摩罗什译，天台宗根本经典" },
      { title: "正法华经", description: "竺法护译，法华经最早汉译本" },
      { title: "观普贤菩萨行法经", description: "法华三部之一，忏悔灭罪" },
    ],
  },
  {
    id: "chan",
    name: "禅宗典籍",
    icon: "\u{1F9D8}",
    description: "直指人心、见性成佛，禅宗的核心经典与语录。",
    texts: [
      { title: "六祖大师法宝坛经", description: "禅宗六祖惠能说法，中国佛教唯一称'经'的祖师著作" },
      { title: "景德传灯录", description: "禅宗灯录体代表作，记录历代禅师传承" },
      { title: "碧岩录", description: "圆悟克勤评唱，禅门第一书" },
      { title: "五灯会元", description: "五部灯录汇编，禅宗公案大全" },
    ],
  },
  {
    id: "vinaya",
    name: "律藏精选",
    icon: "\u{1F4CF}",
    description: "佛教戒律典籍，僧团生活与修行规范。",
    texts: [
      { title: "四分律", description: "法藏部律典，汉传佛教最通行的律典" },
      { title: "梵网经", description: "大乘菩萨戒经典" },
      { title: "摩诃僧祇律", description: "大众部律典" },
    ],
  },
  {
    id: "agama",
    name: "阿含/尼柯耶",
    icon: "\u{1F4D6}",
    description: "佛陀原始教法的直接记录，南北传共有的早期经典。",
    texts: [
      { title: "长阿含经", description: "22卷，对应巴利长部，含大般涅槃经等" },
      { title: "中阿含经", description: "60卷，对应巴利中部" },
      { title: "杂阿含经", description: "50卷，对应巴利相应部，最接近原始佛法" },
      { title: "增壹阿含经", description: "51卷，对应巴利增支部" },
    ],
  },
  {
    id: "yogacara",
    name: "唯识经论",
    icon: "\u{1F50D}",
    description: "瑜伽行派（唯识宗）核心经论，深入分析心识结构。",
    texts: [
      { title: "解深密经", description: "唯识学根本经典，三转法轮" },
      { title: "成唯识论", description: "玄奘糅译，唯识学集大成之作" },
      { title: "瑜伽师地论", description: "弥勒说、无著记，100卷瑜伽行派百科全书" },
      { title: "摄大乘论", description: "无著造，唯识学纲要" },
    ],
  },
  {
    id: "avatamsaka",
    name: "华严系经典",
    icon: "\u2728",
    description: "华严宗根本经典，法界缘起、事事无碍的圆融世界观。",
    texts: [
      { title: "大方广佛华严经", description: "实叉难陀译80卷本，华严宗根本经典" },
      { title: "大方广佛华严经（六十华严）", description: "佛驮跋陀罗译60卷本" },
    ],
  },
];
