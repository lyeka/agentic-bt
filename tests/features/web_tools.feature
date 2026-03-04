Feature: Web 工具 — 搜索互联网 + 获取页面内容
  web_search 搜索返回结构化摘要列表，web_fetch 获取 URL 全文。
  搜索需要 SearchAdapter，URL 抓取始终可用。

  # ── web_search ─────────────────────────────────────────────────────────

  Scenario: web_search 返回结构化结果
    Given 一个带 mock 搜索的 Kernel
    When 调用 web_search query "Python 教程"
    Then 返回 count 大于 0
    And 每条结果包含 title url snippet

  Scenario: web_search 支持域名过滤
    Given 一个带 mock 搜索的 Kernel
    When 调用 web_search query "行情" domains "github.com"
    Then mock adapter 收到 domains 包含 "github.com"

  Scenario: web_search 限制最大结果数为 10
    Given 一个带 mock 搜索的 Kernel
    When 调用 web_search query "test" max_results 20
    Then mock adapter 收到 max_results 为 10

  Scenario: web_search 搜索失败返回 error
    Given 一个会抛异常的 mock 搜索 Kernel
    When 调用 web_search query "fail"
    Then 返回结果包含 error

  # ── web_fetch ──────────────────────────────────────────────────────────

  Scenario: web_fetch 获取页面内容
    Given 一个带 web_fetch 的 Kernel
    When mock HTTP 返回 "Hello World" 并调用 web_fetch url "https://example.com"
    Then 返回 content 包含 "Hello World"
    And 返回 url 为 "https://example.com"

  Scenario: web_fetch 超长内容自动截断
    Given 一个带 web_fetch 的 Kernel
    When mock HTTP 返回超长内容并调用 web_fetch url "https://example.com/long"
    Then 返回 truncated 为 True
    And 返回 chars 小于原始内容长度

  Scenario: web_fetch 无效 URL 返回 error
    Given 一个带 web_fetch 的 Kernel
    When 调用 web_fetch url "not-a-url"
    Then 返回结果包含 error

  Scenario: web_fetch 网络错误返回 error
    Given 一个带 web_fetch 的 Kernel
    When mock HTTP 抛出网络错误并调用 web_fetch url "https://unreachable.invalid"
    Then 返回结果包含 error

  # ── 条件注册 ───────────────────────────────────────────────────────────

  Scenario: 无 search adapter 时只注册 web_fetch
    Given 一个无 search adapter 的 Kernel
    Then Kernel 已注册工具 "web_fetch"
    And Kernel 未注册工具 "web_search"
