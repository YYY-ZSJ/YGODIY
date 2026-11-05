"""单次玩家任务的可选约计费用上限；仅在请求之间检查，不改输出参数。"""

from decimal import Decimal

from .model_info import prices
from .providers import ServiceError


class BudgetPause(ServiceError):
    pass


class TaskBudget:
    def __init__(self, config, saved=None):
        self.limit = Decimal(str(config.get("task_cost_limit", 0)))
        self.state = dict(saved or {})
        self.state.setdefault("spent", "0")
        self.state.setdefault("allowance", str(self.limit))
        if saved and self.state.pop("extend_on_resume", False) and self.limit:
            self.state["allowance"] = str(max(self.spent, Decimal(self.state["allowance"])) + self.limit)
        elif saved and self.limit and self.state.get("limit") != str(self.limit):
            self.state["allowance"] = str(self.spent + self.limit)
        self.state["limit"] = str(self.limit)

    @property
    def spent(self):
        return Decimal(self.state["spent"])

    def reason(self, config):
        if not self.limit:
            return ""
        rates = prices(config)
        if not rates:
            return "当前模型单价未知，费用限制已暂停任务；请在高级补全单价，或关闭费用上限后继续。"
        currency = rates.get("currency", "CNY")
        if self.state.get("currency", currency) != currency:
            return "本任务前后计价币种不同，无法合并费用；请恢复原币种，或关闭费用上限后继续。"
        self.state["currency"] = currency
        if self.state.get("unknown"):
            return "部分请求用量未知，无法继续核算任务费用；请检查用量记录，关闭费用上限后再继续。"
        if self.spent >= Decimal(self.state["allowance"]):
            self.state["extend_on_resume"] = True
            return ("已达到本任务约计费用上限（约 %s %s / %s）。已保留进度；"
                    "点击「继续」将再增加 %s %s 额度，可在高级调整或关闭。") % (
                        currency, self.state["spent"], self.state["allowance"], currency, self.limit)
        return ""

    def before_request(self, config):
        reason = self.reason(config)
        if reason:
            raise BudgetPause(reason)

    def record(self, info):
        cost, usage, rates = info.get("cost", {}), info["usage"], info.get("rates")
        # 缓存明细缺失但输入输出齐全时，按所有输入的最高档保守估算。
        if not cost.get("known") and rates and usage.get("input_known") and usage.get("output_known"):
            total = (Decimal(usage["input_tokens"]) * Decimal(str(max(rates[k] for k in ("input", "cache_read", "cache_write")))) +
                     Decimal(usage["output_tokens"]) * Decimal(str(rates["output"]))) / Decimal(1000000)
            cost = {"known": True, "currency": rates.get("currency", "CNY"), "total": str(total)}
            self.state["conservative"] = True
        if not cost.get("known"):
            self.uncertain()
            return
        currency = cost.get("currency", "CNY")
        if self.state.get("currency", currency) != currency:
            self.uncertain()
            return
        self.state.update(currency=currency, spent=str(self.spent + Decimal(cost["total"])))

    def uncertain(self):
        self.state["unknown"] = True

    def snapshot(self):
        return dict(self.state)


def for_task(config, resume=None):
    if "_task_budget" not in config:
        config = dict(config, _task_budget=TaskBudget(config, (resume or {}).get("budget")))
    return config
