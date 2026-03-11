Feature: Sub-Agent 子代理系统
  主 Agent 可将任务委派给子代理。
  子代理有独立上下文、受限工具集和输出契约。
  子代理的领域由 system_prompt 定义，框架不预设领域。

  Background:
    Given 一个临时 subagent 工作区

  # ── 文件发现与加载 ──

  Scenario: 从 subagents 目录发现 md 文件并加载
    Given subagent 根目录存在定义 "coder"
    When 加载 subagent 文件
    Then 加载结果包含 "coder"
    And 诊断信息为空

  Scenario: frontmatter 缺少 description 时跳过并产生诊断
    Given subagent 根目录存在无 description 定义 "broken"
    When 加载 subagent 文件
    Then 加载结果不包含 "broken"
    And 诊断信息包含 code "missing_description"

  Scenario: 名称冲突时保留先加载项并产生诊断
    Given subagent 根目录存在定义 "coder"
    And 第二个根目录也存在定义 "coder"
    When 从两个根目录加载 subagent 文件
    Then 加载结果包含 "coder"
    And 诊断信息包含 code "name_collision"

  Scenario: body 中的 output_protocol 标签被提取为 output_guide
    Given subagent 根目录存在带 output_protocol 的定义 "writer"
    When 加载 subagent 文件
    Then "writer" 的 output_guide 为 "返回完整文档"

  # ── 纯函数 ──

  Scenario: filter_schemas 白名单过滤
    Given 工具 schemas 包含 "read" "write" "bash"
    When 按白名单 "read" "write" 过滤
    Then 过滤结果仅包含 "read" "write"

  Scenario: filter_schemas 黑名单过滤
    Given 工具 schemas 包含 "read" "write" "bash"
    When 按黑名单 "bash" 过滤
    Then 过滤结果仅包含 "read" "write"

  Scenario: filter_schemas 白名单和黑名单同时生效
    Given 工具 schemas 包含 "read" "write" "bash" "compute"
    When 按白名单 "read" "write" "bash" 黑名单 "bash" 过滤
    Then 过滤结果仅包含 "read" "write"

  # ── 基础委派 ──

  Scenario: 委派任务后获得执行结果
    Given 一个 mock LLM 返回 "任务完成"
    And 一个注册了 "helper" 的 SubAgentSystem
    When 调用 "helper" 执行任务 "做个总结"
    Then 子代理结果文本包含 "任务完成"

  Scenario: 子代理使用工具完成任务后返回结果
    Given 一个 mock LLM 先调工具再返回 "计算完毕"
    And 一个注册了 "analyst" 的 SubAgentSystem
    When 调用 "analyst" 执行任务 "计算指标"
    Then 子代理结果文本包含 "计算完毕"
    And 子代理 metadata 中 tools_used 大于 0

  Scenario: 子代理执行轮次耗尽时返回已有结果
    Given 一个 mock LLM 持续调用工具不停止
    And 一个注册了 max_rounds 为 2 的 "looper"
    When 调用 "looper" 执行任务 "无限循环"
    Then 子代理结果包含 rounds 等于 2

  Scenario: 子代理 LLM 调用失败时返回错误信息
    Given 一个 mock LLM 抛出异常
    And 一个注册了 "failer" 的 SubAgentSystem
    When 调用 "failer" 执行任务 "会失败"
    Then 子代理结果文本包含 "error"

  # ── 通信协议 ──

  Scenario: output_guide 注入子代理 system prompt
    Given 一个带 output_guide 的 SubAgentDef "formatter"
    And 一个捕获 LLM 调用的 mock
    When 通过 run_subagent 执行 "formatter"
    Then LLM 收到的 system prompt 包含 "<output_protocol>"

  Scenario: 无 output_guide 时 system prompt 不含 output_protocol 标签
    Given 一个无 output_guide 的 SubAgentDef "plain"
    And 一个捕获 LLM 调用的 mock
    When 通过 run_subagent 执行 "plain"
    Then LLM 收到的 system prompt 不包含 "<output_protocol>"

  Scenario: 返回结果包含质量元数据
    Given 一个 mock LLM 返回 "done"
    And 一个注册了 "meta" 的 SubAgentSystem
    When 调用 "meta" 执行任务 "check"
    Then 子代理结果 metadata 包含 "rounds"
    And 子代理结果 metadata 包含 "response_chars"

  # ── 工具隔离 ──

  Scenario: 子代理只能使用白名单内的工具
    Given 父级工具集包含 "read" "write" "bash"
    And SubAgentDef 白名单为 "read" "write"
    When 生成子代理工具 schemas
    Then 子代理工具仅包含 "read" "write"

  Scenario: 子代理无法调用被黑名单禁止的工具
    Given 父级工具集包含 "read" "write" "bash"
    And SubAgentDef 黑名单为 "bash"
    When 生成子代理工具 schemas
    Then 子代理工具仅包含 "read" "write"

  Scenario: 子代理无法调用 create_subagent 防递归
    Given 父级工具集包含 "read" "create_subagent"
    And SubAgentDef 未设置工具过滤
    When 生成子代理工具 schemas
    Then 子代理工具不包含 "create_subagent"

  # ── 资源管控 ──

  Scenario: token 超预算时优雅终止并标记 budget_exhausted
    Given 一个 mock LLM 每次消耗 30000 tokens
    And SubAgentDef token_budget 为 50000
    When 通过 run_subagent 执行
    Then 子代理结果 metadata budget_exhausted 为 true

  Scenario: 执行超时时返回部分结果并标记 timed_out
    Given 一个 mock LLM 每次延迟 2 秒
    And SubAgentDef timeout_seconds 为 1
    When 通过 run_subagent 执行
    Then 子代理结果 metadata timed_out 为 true

  # ── 生命周期管理 ──

  Scenario: 注册子代理后工具列表包含 ask 工具
    Given 一个空的 SubAgentSystem
    When 注册 SubAgentDef "expert"
    Then as_tool_defs 包含 "ask_expert"

  Scenario: 移除子代理后工具从列表消失
    Given 一个空的 SubAgentSystem
    And 已注册 SubAgentDef "expert"
    When 移除 "expert"
    Then as_tool_defs 不包含 "ask_expert"

  Scenario: 子代理总数超过上限时注册被拒绝
    Given 一个 max_subagents 为 1 的 SubAgentSystem
    And 已注册 SubAgentDef "first"
    When 尝试注册 SubAgentDef "second"
    Then 注册结果包含错误

  Scenario: 注册子代理后 team_prompt 包含描述
    Given 一个空的 SubAgentSystem
    When 注册 SubAgentDef "expert" 描述 "领域专家"
    Then team_prompt 包含 "expert"
    And team_prompt 包含 "领域专家"

  Scenario: Kernel boot 后 system prompt 包含 team 描述
    Given subagent 根目录存在定义 "coder"
    When Kernel 使用该 subagent 根目录启动
    Then kernel system prompt 包含 "<team>"
    And kernel system prompt 包含 "coder"

  # ── 内置子代理 ──

  Scenario: 从项目目录加载内置 technician 子代理
    Given 项目 subagent 目录包含 "technician" 定义文件
    When 加载项目 subagent 文件
    Then 加载结果包含 "technician"
    And "technician" 的工具白名单为 "market_ohlcv" 和 "compute"
    And "technician" 的 token_budget 为 40000

  Scenario: 从项目目录加载内置 researcher 子代理
    Given 项目 subagent 目录包含 "researcher" 定义文件
    When 加载项目 subagent 文件
    Then 加载结果包含 "researcher"
    And "researcher" 的工具白名单为 "web_search" 和 "web_fetch"
    And "researcher" 的 token_budget 为 50000
