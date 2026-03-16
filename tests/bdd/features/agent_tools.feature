Feature: Agent 工具系统 — read/write/edit/bash 通用原语 + 路径安全
  Agent 工具层提供文件操作和 shell 执行能力，
  双信任区域（workspace + cwd）保障路径安全，
  截断机制防止输出爆 token。

  Background:
    Given 一个临时工作区

  # ── read ──────────────────────────────────────────────────────────────

  Scenario: read 读取文件带行号
    Given 工作区文件 "hello.txt" 内容为 "line1\nline2\nline3"
    When 调用 read 工具 path="hello.txt"
    Then 返回 content 包含 "1| line1"
    And 返回 content 包含 "3| line3"
    And 返回 total_lines 为 3

  Scenario: read 分页 offset/limit
    Given 工作区文件 "big.txt" 内容为 10 行
    When 调用 read 工具 path="big.txt" offset=3 limit=2
    Then 返回 content 首行为 "3| line3"
    And 返回 content 共 2 行

  Scenario: read 大文件截断
    Given 工作区文件 "huge.txt" 内容为 3000 行
    When 调用 read 工具 path="huge.txt"
    Then 返回 truncated 为 true
    And 返回 next_offset 存在

  Scenario: read 目录列表
    Given 工作区目录 "notes" 含文件 "a.md" 和 "b.md"
    When 调用 read 工具 path="notes"
    Then 返回 entries 包含 "a.md" 和 "b.md"

  Scenario: read 二进制文件拒绝
    Given 工作区二进制文件 "data.bin"
    When 调用 read 工具 path="data.bin"
    Then 返回 error 包含 "二进制"

  Scenario: read 文件不存在
    When 调用 read 工具 path="ghost.txt"
    Then 返回 error 包含 "不存在"

  # ── edit ──────────────────────────────────────────────────────────────

  Scenario: edit 精确替换并返回 diff
    Given 工作区文件 "code.py" 内容为 "x = 1\ny = 2\nz = 3"
    When 调用 edit 工具 path="code.py" old="y = 2" new="y = 42"
    Then 返回 status 为 "ok"
    And 返回 diff 包含 "+y = 42"
    And 返回 first_changed_line 为 2

  Scenario: edit 模糊匹配（行尾空白）
    Given 工作区文件 "space.txt" 内容为 "hello   \nworld"
    When 调用 edit 工具 path="space.txt" old="hello" new="hi"
    Then 返回 status 为 "ok"

  Scenario: edit 唯一性检查
    Given 工作区文件 "dup.txt" 内容为 "foo\nbar\nfoo"
    When 调用 edit 工具 path="dup.txt" old="foo" new="baz"
    Then 返回 error 包含 "2 处匹配"

  Scenario: edit 未找到匹配
    Given 工作区文件 "miss.txt" 内容为 "hello world"
    When 调用 edit 工具 path="miss.txt" old="xyz" new="abc"
    Then 返回 error 包含 "未找到"

  # ── write ─────────────────────────────────────────────────────────────

  Scenario: write 创建文件并返回字节数
    When 调用 write 工具 path="new.txt" content="你好世界"
    Then 返回 status 为 "ok"
    And 返回 bytes_written 大于 0
    And 工作区文件 "new.txt" 存在

  Scenario: write 自动创建目录
    When 调用 write 工具 path="deep/nested/file.txt" content="ok"
    Then 返回 status 为 "ok"
    And 工作区文件 "deep/nested/file.txt" 存在

  # ── bash ──────────────────────────────────────────────────────────────

  Scenario: bash 执行简单命令
    When 调用 bash 工具 command="echo hello"
    Then 返回 exit_code 为 0
    And 返回 output 包含 "hello"

  Scenario: bash 非零退出码
    When 调用 bash 工具 command="exit 42"
    Then 返回 exit_code 为 42
    And 返回 error 包含 "退出码"

  Scenario: bash 超时
    When 调用 bash 工具 command="sleep 10" timeout=1
    Then 返回 error 包含 "超时"

  Scenario: bash 大输出截断
    When 调用 bash 工具 command 输出 3000 行
    Then 返回 truncated 为 true

  # ── 路径安全 ──────────────────────────────────────────────────────────

  Scenario: 信任区域内文件可直接操作
    Given 工作区文件 "safe.txt" 内容为 "ok"
    When 调用 read 工具 path="safe.txt"
    Then 返回 content 包含 "ok"

  Scenario: 信任区域外文件需要确认
    Given 确认回调返回拒绝
    When 调用 read 工具 path="/etc/hostname"
    Then 返回 error 包含 "拒绝"
