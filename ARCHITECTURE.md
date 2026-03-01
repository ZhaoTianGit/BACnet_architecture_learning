# 🏗️ BACnet Framework — Architecture Guide for Beginners

## The Big Picture — What We Built and Why

Before looking at any code, understand this one idea:

> **Good code is like a restaurant.**  
> The chef doesn't serve tables. The waiter doesn't cook. The manager doesn't wash dishes.  
> Each person has ONE clear job. They work together through a clear process.

Our framework works the same way. Every file has **one job**.

---

## The File Map

```
bacnet_framework/
│
├── main.py                  ← The Manager (wires everyone together)
│
├── config/
│   └── settings.py          ← The Menu (all settings in one place)
│
├── core/
│   ├── hooks.py             ← The Intercom System (event bus)
│   ├── transport.py         ← The Waiter (carries data to/from network)
│   └── runner.py            ← The Chef (decides what steps to take)
│
└── hooks/
    └── builtin.py           ← The Appliances (plug-in extensions)
```

---

## Concept 1 — Separation of Concerns

**The Problem this solves:**  
Imagine you wrote everything in one 300-line file.  
Now your boss says "add Slack alerts on failure."  
You have to read all 300 lines to find the right place. Easy to break other things.

**The Solution:**  
Each file does ONE thing. To add Slack alerts, you only touch `hooks/builtin.py`.  
The BACnet network code (`transport.py`) never changes. You can't accidentally break it.

```
❌ One big file — everything tangled together:
   bms_test.py  (config + network + test logic + logging + alerts = 400 lines)

✅ Separated files — each does one job:
   config/settings.py   (50 lines)
   core/transport.py    (100 lines)
   core/runner.py       (150 lines)
   hooks/builtin.py     (100 lines)
   main.py              (60 lines)
```

---

## Concept 2 — The Hook System (Most Important!)

### What is a Hook?

A hook is a **named slot** in your code where you can plug in custom behaviour,  
**without editing the core logic.**

### Real World Example — Git Hooks

When you run `git commit`, Git has hook slots:
```
pre-commit  → runs YOUR script before commit (e.g. run tests)
post-commit → runs YOUR script after commit  (e.g. send notification)
```

You didn't write Git. But you can extend it through its hooks.

### Our Framework's Hooks

```
"before_write"  → fires just before any BACnet write
"after_write"   → fires just after a successful write
"before_read"   → fires just before any BACnet read
"after_read"    → fires just after a successful read
"on_pass"       → fires when the entire test sequence passes
"on_fail"       → fires when any step throws an exception
"on_restore"    → fires after Out-Of-Service is restored
```

### How to Plug In a Hook

**Method A — Decorator (clean syntax):**
```python
@hooks.register("on_fail")
async def my_alert(ctx):
    print(f"Test failed! Error = {ctx['error']}")
```

**Method B — Direct registration (good for external functions):**
```python
hooks.register_fn("on_fail", my_alert)
```

**Both do exactly the same thing.** The `@` decorator is just cleaner to read.

### The ctx Dictionary

Every hook receives a `ctx` (context) dictionary telling it what happened:
```python
# on_fail ctx example:
{
    "result": <TestResult object>,
    "error":  "Step 2 FAILED: out-of-service did not assert True",
    "target": "192.168.100.183:63205"
}

# after_write ctx example:
{
    "step":     3,
    "property": "present-value",
    "value":    31.0,
    "priority": 8
}
```

### Hook Power — Adding Features Without Touching Core Logic

**Scenario:** Your manager says "log all tests to a CSV file."

Without hooks (bad):
```python
# You have to open runner.py and edit the core logic
async def _step_inject(self, result):
    await self._transport.write(...)
    # ADD THIS — but now runner.py knows about CSV files. Wrong!
    with open("log.csv", "a") as f:
        f.write(f"{value}\n")
```

With hooks (good):
```python
# You write a NEW function in hooks/builtin.py — don't touch runner.py at all
async def csv_reporter(ctx):
    with open("log.csv", "a") as f:
        f.write(f"{ctx['value']}\n")

# Register it in main.py — one line
hooks.register_fn("after_write", csv_reporter)
```

`runner.py` never changes. You extended the system by adding to it, not editing it.  
This is called the **Open/Closed Principle** — open for extension, closed for modification.

---

## Concept 3 — Dependency Injection

### The Problem

```python
# BAD — TestRunner creates its own transport
class TestRunner:
    def __init__(self):
        self.transport = BACnetTransport()   # hardcoded!
```

Problems:
- Can't test TestRunner without real BACnet hardware
- Can't swap BACnetTransport for a mock or different library
- Creating TestRunner always creates a network connection — even in unit tests

### The Solution

```python
# GOOD — TestRunner receives transport from outside
class TestRunner:
    def __init__(self, transport, hooks, cfg):
        self.transport = transport   # injected!
        self.hooks = hooks
        self.cfg = cfg
```

Benefits:
- Pass a `FakeTransport` in unit tests — no hardware needed
- Swap transport for a different BACnet library — TestRunner doesn't care
- Easier to read: the constructor tells you exactly what TestRunner needs

This pattern is called **Dependency Injection (DI)**.  
"Injection" just means "passed in from outside" — not scary!

---

## Concept 4 — Context Manager (`async with`)

### The Problem

```python
# BAD — socket might not close if exception occurs
transport = BACnetTransport(cfg)
await transport.connect()
await runner.run()     # ← if this crashes...
await transport.disconnect()   # ← this never runs! socket stays open!
```

### The Solution

```python
# GOOD — socket ALWAYS closes, even if exception occurs
async with BACnetTransport(cfg) as transport:
    await runner.run()   # ← even if this crashes...
# socket is GUARANTEED closed here by __aexit__()
```

The `async with` pattern calls `__aexit__()` automatically —  
whether the code inside succeeded, failed, or crashed.

This is how you write "guaranteed cleanup" code.

---

## Concept 5 — Data Classes

### The Problem

```python
# BAD — loose variables, easy to lose track of what belongs together
TARGET_IP       = "192.168.100.183"
TARGET_PORT     = 63205
LOCAL_IP        = "192.168.100.183"
LOCAL_PORT      = 47810
DEVICE_ID       = 9999
TEST_VALUE      = 31.0
WRITE_PRIORITY  = 8
```

### The Solution

```python
# GOOD — grouped into logical namespaces
@dataclass
class DUTConfig:
    ip:   str = "192.168.100.183"
    port: int = 63205

@dataclass
class TestConfig:
    test_value:     float = 31.0
    write_priority: int   = 8

# Usage — reads like plain English:
cfg.dut.ip         # not just "TARGET_IP"
cfg.test.test_value # not just "TEST_VALUE"
```

Related settings live together. Unrelated settings stay separate.

---

## How to Add New Features (The Plug-and-Play Flow)

### Example: "Email me when a test fails"

**Step 1** — Write your hook function in `hooks/builtin.py`:
```python
async def email_on_fail(ctx: dict) -> None:
    import smtplib
    error = ctx.get("error", "unknown")
    # send email with error details...
    print(f"Email sent: test failed — {error}")
```

**Step 2** — Register it in `main.py` (one line):
```python
hooks.register_fn("on_fail", email_on_fail)
```

**That's it.** You didn't touch `runner.py`, `transport.py`, or `settings.py`.

---

### Example: "Test a different BACnet object"

**Step 1** — Update config in `main.py`:
```python
cfg.dut.object_id = "analog-value,2"   # target AV:2 instead of AV:0
cfg.test.test_value = 25.0             # inject 25°C instead of 31°C
```

**That's it.** No other file changes.

---

### Example: "Run two different test scenarios back to back"

```python
# In main.py:

# Scenario A: test setpoint
cfg.dut.object_id = "analog-value,0"
cfg.test.test_value = 31.0
runner_a = TestRunner(cfg, transport, hooks)
result_a = await runner_a.run()

# Scenario B: test a different setpoint
cfg.dut.object_id = "analog-value,1"
cfg.test.test_value = 18.0
runner_b = TestRunner(cfg, transport, hooks)
result_b = await runner_b.run()
```

**That's it.** Transport and hooks are shared. Runners are swapped.

---

## Summary — The 8 Architecture Lessons

| # | Lesson | One-Line Summary |
|---|--------|-----------------|
| 1 | **Configuration Layer** | All settings in one file, no magic numbers scattered in code |
| 2 | **Hook System** | Named slots where you plug in custom behaviour without editing core logic |
| 3 | **Separation of Concerns** | Each file does ONE job — network, config, orchestration, extensions |
| 4 | **Orchestrator Pattern** | Runner knows the ORDER but delegates actual work to specialists |
| 5 | **Dependency Injection** | Pass dependencies in from outside — never hardcode them |
| 6 | **Plugin System** | Pre-built extensions you opt into — not forced on you |
| 7 | **Context Manager** | `async with` guarantees cleanup even when exceptions occur |
| 8 | **Composition Root** | One place (`main.py`) wires all the pieces together |

---

## The Three Questions to Ask When Writing Any New Code

1. **"Does this belong in config?"** — Is it a value that might change? → `settings.py`
2. **"Does this belong in a hook?"** — Is it an optional extension that reacts to events? → `hooks/builtin.py`
3. **"Does this belong in transport or runner?"** — Is it core logic? Which layer does it serve?

If you answer these three questions before writing, your code will naturally be modular.
