Feature: TUI 终端界面 — 投资助手交互终端
  TUI 是 Kernel 的展示层适配器。
  核心契约：用户输入到达 Kernel，Kernel 回复呈现到界面。

  Scenario: 发送消息获得回复
    Given TUI 使用 Mock Kernel 启动
    When 用户输入 "你好"
    Then Kernel.turn 被调用且参数为 "你好"
    And 聊天区域包含助手回复

  Scenario: 空输入不触发调用
    Given TUI 使用 Mock Kernel 启动
    When 用户发送空白消息
    Then Kernel.turn 未被调用

  Scenario: 保护文件写入弹出确认
    Given TUI 使用 Mock Kernel 启动
    And Kernel 的 confirm 回调已注册
    When confirm 回调被触发路径为 "soul.md"
    Then 界面出现确认对话框

  Scenario: 工具调用期间显示进度
    Given TUI 使用 Mock Kernel 启动
    When Kernel 触发 tool.call.start 事件 name="market_ohlcv"
    Then 聊天区域包含 "market_ohlcv" 进度文本

  Scenario: 恢复已有会话历史
    Given 一个包含 3 条用户消息的 Session
    When TUI 以该 Session 启动
    Then 聊天区域显示 3 条历史消息

  Scenario: 流式输出逐步渲染
    Given TUI 使用 Mock Kernel 启动
    When Kernel 触发 llm.chunk 事件内容为 "你好世界"
    Then 聊天区域包含流式文本 "你好世界"

  Scenario: 新建会话清空聊天
    Given TUI 使用 Mock Kernel 启动
    When 用户输入 "你好"
    And 用户创建新会话
    Then 聊天区域为空

  Scenario: 助手回复显示耗时
    Given TUI 使用 Mock Kernel 启动
    When 用户输入 "分析"
    Then 聊天区域包含耗时元数据

  Scenario: Kernel 异常时显示错误提示
    Given TUI 使用 Mock Kernel 启动
    When Kernel 在 turn 中抛出异常
    Then 聊天区域包含错误提示
