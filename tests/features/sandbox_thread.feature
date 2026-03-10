Feature: 沙箱线程安全 — 非主线程环境自动降级
  exec_compute 在主线程使用 signal.SIGALRM 超时，
  在非主线程（如 asyncio.to_thread）自动降级为 ThreadPoolExecutor 超时。

  Scenario: 主线程正常执行
    Given 一个示例 DataFrame
    When 在主线程执行 compute "len(df)"
    Then 结果 result 为 5

  Scenario: 子线程正常执行
    Given 一个示例 DataFrame
    When 在子线程执行 compute "len(df)"
    Then 结果 result 为 5

  Scenario: 子线程中死循环触发超时
    Given 一个示例 DataFrame
    When 在子线程执行 compute "while True: pass" 超时 100ms
    Then 结果包含超时错误
