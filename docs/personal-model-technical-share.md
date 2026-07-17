# Persome Personal Memory

> 归档说明：本文件保留为早期 Markdown 工作稿。后续唯一主稿为
> [`personal-model-technical-share.html`](personal-model-technical-share.html)。

## 从 AX Tree 到 Agent Context

> 团队工程师技术分享：Mac 上持续发生的活动，怎样沉淀为可召回、可解释的个人结构。

## 开篇 · Personal Memory 是什么、为什么需要它

> **一句话：**普通 Agent 只能看见当前会话；Personal Memory 让它在进入任务时，就知道当前进度、相关人物和用户反复表现出的工作方式，也就是说能够知道用户的建模，知道用户是个怎么样的人

### 先对齐几个术语

- **AX Tree**：macOS Accessibility 暴露的窗口、控件、焦点和文本结构。
- **Event**：事件：窗口切换、输入、点击或内容变化。它只说明“发生了变化”。
- **Capture**：系统在某个时刻保存的一帧证据，包含前台应用、焦点元素、可见文本和 URL 等信息。
- **Personal Memory**：当前用户从多次活动中形成的事实、关系和行为模式。它可以被检查、修正和召回。
- **Memory Formation**：Event 经过过滤、状态构造和证据门禁，逐步进入 Personal Memory 的过程。
- **Memory Recall**：当前情境从 Personal Memory 中选择相关部分，并组织成 Agent 可以使用的上下文。



### 为什么普通 Agent 不能直接接着昨天工作？

第二天，小张重新打开 Claude Code，继续处理昨天没有完成的项目 A。对一个普通 Agent 来说，这是一次新的会话。

它只看得到当前仓库和小张刚刚输入的内容。小张需要重新解释三件事：

```text
现在做到哪里？
这件事正在和谁一起做？
自己通常会怎样推进这类修改？
```

这里有两个问题叠在一起。

1. **会话上下文会重置。** 昨天的任务进度和协作信息不会自动进入今天的 Claude Code。
2. **活动日志不等于个人结构。** 即使系统保存了昨天的全部屏幕内容，它仍然不知道哪些是当前项目状态，哪些是稳定关系，哪些做法已经反复出现。

所以目标不是把更多日志塞进 Prompt，而是把活动先组织成可以长期使用的结构，再由当前任务选择相关部分。

### Persome 怎么解决？

Persome 把问题拆成两条线：

```text
Memory Formation
App / AX Tree → Event → Capture → 当前状态 → Personal Memory

Memory Recall
当前情境 → Memory Attention Heads → 相关结构 → Agent Context
```

前一条线回答“Memory 从哪里来”，后一条线回答“什么时候应该想起什么”。

### 整条技术主线只做三件事

1. **看清楚。** 从连续、重复、敏感的 Mac 事件中保留真正有意义的证据。
2. **沉淀得足够谨慎。** LLM 可以提出候选，但事实、关系和行为模式必须经过确定性门禁与重复证据。
3. **在正确的时刻召回。** 当前项目、人物和任务决定哪些 Memory 应该进入 Agent Context，其余内容继续留在模型中。

Prediction 与 Training Loop 放在最后作为展望。当前先把已经实现的形成、召回、证据和工程边界讲清楚。

## 交互主图：Memory 形成与 Memory Recall

静态 Mermaid 只能展示一次性的总流程，无法承担现场逐层展开。全场主图改为一个可点击的交互视图：

[打开 Memory 形成与 Recall 交互图](/Users/liyingliang/.cursor/projects/Users-liyingliang-opensource-personal-model/canvases/persome-memory-flow.canvas.tsx)

主图只保留两条线：

```text
Memory 形成：
App / AX Tree → 数据收集 → 事件过滤 → S1 证据帧
→ 状态形成 → Memory 提炼 → Memory 沉淀

Memory Recall：
当前情境 → Memory Attention Heads → 候选融合
→ 关系链与事实引用 → Agent Context 交付
```

点击任一阶段后，页面会横向展开该阶段的子流程，并纵向展示：

- 输入与输出
- 具体收集器或处理子阶段
- 必须守住的工程不变量
- 对应代码入口
- 为分享结论所需的埋点与评测

这两条线只在一个位置汇合：Memory 形成线产出可寻址的 Personal Memory，Recall 线再用当前情境选择其中相关的一部分。

## 0 · 走一个实例：Agent 最终应该知道什么

这一章先不讲 Point、Line、Face，也不讲检索算法。先站在 Agent 的位置，确定最终需要拿到什么。

### 场景：第二天重新打开 Claude Code

小张再次进入项目 A 的仓库。Claude Code 此刻需要的不是“昨天发生了什么”的完整流水，而是与当前工作直接相关的一块个人上下文：

```text
项目 A 当前正在处理数据解析稳定性。昨天已经完成重试路径修复，
相关测试通过；接下来还需要补浏览器验证和完整测试。[事实引用 1]

小李是项目 A 的主要协作者，最近参与了数据契约和重试方案的讨论。
[事实引用 2]

小张在跨模块修改前通常先复现问题、补回归测试，再扩大修改范围。
[事实引用 3]
```

先不看引用，正文只有三句话。

第一句话描述一个刚刚发生、可以被验证的项目状态。它变化得快，明天可能就会被新进度覆盖。

第二句话描述小张、小李和项目 A 之间的关系。它不是一次操作结果，而是从多次协作中逐渐确认出来的。

第三句话描述小张反复出现的工作方式。一次“先写测试”不足以得出这个判断，只有多个任务中出现同样顺序，系统才有资格把它写成模式。

现在再给这三种信息命名：

- 近期事实（Fact）：某件具体事情当前是什么状态。
- 人物关系（Relation）：人与人、人与项目之间存在什么稳定联系。
- 行为模式（Behavior Pattern）：同一种做法是否跨任务反复出现。

`[事实引用]` 不属于第四种 Memory。它是附着在每一句判断上的证据入口，用来回答：“系统为什么有资格这样说？”

```text
Recall 中的一句话
→ 对应的 Fact / Relation / Behavior Pattern
→ 支撑它的一个或多个低层 Fact
→ 每个 Fact 对应的 Raw Evidence
```

这段 Recall 没有复述昨天的全部屏幕活动。当前任务只激活与项目 A、小李和当前修改方式相关的结构。

### 事实引用 1：近期项目事实

`[事实引用 1]` 支撑“项目 A 的重试路径已经修复”。

展开 [事实引用 1]

```text
Fact
  项目 A 的重试路径已完成修复，相关测试通过。

Raw Evidence
  [Claude Code · owner-authored]
  “重试路径已经修复，相关测试通过。”

  [Terminal · tool result]
  “tests passed”

Evidence Scope
  当前项目 A Session，重试路径相关窗口
```

这里的 Fact 是规范化后的项目状态。Raw Evidence 保留当时的逐字内容。Recall 展示 Fact，事实引用负责把它带回原始证据。

### 事实引用 2：人物与项目关系

`[事实引用 2]` 支撑“当前工作与小李有关”。“主要协作者”不能来自一次同屏出现，它需要多次独立协作事实。

展开 [事实引用 2]

```text
Relation
  self knows 小李，label = collaborator
  self participates_in 项目 A
  小李 participates_in 与项目 A 相关的多个 Activity

Supporting Facts
  小李参与了项目 A 的数据契约讨论。
  小李与小张共同检查了重试方案。
  小李在多个项目 A Session 中持续出现。

Raw Evidence
  [Chat · 小李 received]
  “数据契约部分我来一起看。”

  [Claude Code · owner-authored]
  “和小李对齐重试方案后继续修改。”
```

代码中的 Relation 使用封闭 Predicate。“协作者”更适合作为关系标签；“主要”则要由跨 Session 的独立证据数量、时间跨度和共同 Activity 支撑，不能只让 LLM 写一个形容词。

### 事实引用 3：行为模式

`[事实引用 3]` 支撑“小张通常先验证，再扩大修改范围”。一次任务只能成为 Supporting Fact，不能直接生成行为模式。

展开 [事实引用 3]

```text
Behavior Pattern
  小张在跨模块修改前通常先复现问题并补回归测试。

Supporting Facts
  项目 A：先复现重试失败，再修改实现。
  项目 B：先补解析回归测试，再调整数据结构。
  项目 C：先运行完整门禁，再扩大重构范围。

Raw Evidence
  每条 Supporting Fact 分别引用对应 Session 中的小张输入、
  测试命令与结果，以及最终完成状态。
```

行为模式的引用链比普通 Fact 更长：

```text
Recall Claim
→ Behavior Pattern
→ 多个独立 Supporting Facts
→ 每个 Fact 各自对应的 Raw Evidence
```

高层结构是否可信，不取决于句子写得多像用户，而取决于它能否回到多个相互独立的低层事实。

### Recall 不应该交付什么

这次 Recall 不应包含：

- 昨天全部 Capture、Timeline 或 Event Memory。
- 与项目 A 无关的小张画像。
- 对小李性格和能力的无依据推断。
- 只由一次事件推断出的“小张习惯”。
- 没有事实引用的建议或行动指令。

Recall 的职责是交付与当前情境有关的事实、关系和行为模式。它不在这里决定下一步应该怎么做，那属于 Prediction 与 Action Policy。

### 当前实现边界

上面的格式定义了分享中的目标交付形态。当前代码已经保存 Memory Delta 中的 Quote、Session 和时间窗口，也能从 Point、Relation 和高层结构向下读取部分 Receipt。

但 Point 目前没有直接保存 `delta_id`、`session_id` 或精确 `capture_id`，Timeline 也只保存 `capture_count`。因此，逐句 Fact 到精确 Raw Capture 的引用链还没有完全闭合。这项缺口会在后文单独说明，不把目标界面写成已经实现的能力。

### 这一章要落下的结论

> Recall 不是按时间找回最近内容，而是让当前情境激活相关的个人结构，并让每一句判断都能回到事实与原始证据。

下一步从链路最左侧开始：这些可引用的 Raw Evidence，最初怎样从不同 App 的 AX Tree 中被收集出来？

## 1 · Event 不是 Memory：Mac 上的现实如何留下证据

说明普通 Cocoa 应用、Electron 应用、浏览器、聊天应用和终端分别能从 AX、应用解析器、本地 socket 或 OCR 中取得什么，以及哪些内容必须在隐私边界前被丢弃。

## 2 · “现在”如何形成：连续事件如何变成有边界的状态

沿着 S0 去重、S1 Capture、一分钟 Timeline、确定性 Session 和五分钟 Reducer，解释连续、重复的桌面事件如何变成可重放的当前状态。

## 3 · “过去”如何沉淀：事实、关系和行为模式如何形成

区分 Event Memory 与 Personal Memory，解释 Memory Delta、Quote/Identity/Predicate/Confidence Gate，以及 Point、Line、Face、Volume、Root 的形成速度和证据门槛。

## 4 · 当前情境如何激活个人结构

解释当前项目、人物、应用和任务如何构成 Recall 的问题，相关 Fact、Relation 和 Behavior Pattern 如何被召回，而不是按时间倒出昨天的全部活动。

## 5 · Memory 如何交付给 Agent

解释召回结果如何被裁剪、组织并通过 MCP 交付；每条陈述如何附带 Fact 与 Raw Evidence；哪些信息应当省略，哪些不确定性必须保留。

## 6 · 如何证明它没有丢、没有编，而且真的有用

分别评估事件过滤、状态压缩、Memory 构建、事实引用、Recall 相关性、端到端延迟、成本和故障恢复。运行埋点证明系统如何工作，标注评测回答结果是否正确。

## 7 · 工程复盘：哪些方法可以迁移到下一套系统

总结分层压缩、LLM Proposal 与确定性写入分离、证据优先、双速生长、可恢复水位线和显式降级等工程经验。

## 8 · 展望：从 Recall 走向 Predict Your Next State

说明当前工程已经建立的边界，以及 Prediction、Feedback、Credit Assignment 和 Training Loop 仍需哪些数据与评测。