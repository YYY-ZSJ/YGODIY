"""仅压缩发给模型的结果；本机候选、影响模式和完整审计记录保持完整。"""

MODE_CODES = {"OCG/TCG": "o", "Rush Duel": "r", "超速决斗(Rush Duel)": "r", "RD": "r", "游戏王漫画卡": "m", "漫画卡": "m", "DIY 工作台": "d",
              "旧版卡": "p", "场地中心卡": "f", "卡背": "b"}
MODIFY_TOOLS = {"set_card_fields", "set_effect_blocks", "new_card", "copy_card", "new_pack", "copy_pack", "write_test_scenario", "run_sandbox_test",
                "set_effect_text", "write_custom_lua", "write_card_script", "set_card_data"}


def _mode(value):
    return value.get("id") if isinstance(value, dict) else value


def _snapshot(data):
    if "fields" not in data:
        return data
    result = {key: data[key] for key in ("card_uid", "card_label", "fields", "labels", "session_fields", "candidate", "test_progress") if key in data}
    result["mode"] = _mode(data.get("mode"))
    if data.get("storage_scope") == "editor_session":
        result["scope"] = "editor"
    return result


def _description(data):
    fields = {}
    for row in data.get("fields", []):
        item = {key: row[key] for key in ("type", "choices", "labels", "text_value", "minimum", "maximum", "max_length") if key in row}
        item["affects"] = [MODE_CODES.get(mode, mode) for mode in row.get("affected_modes", [])]
        if row.get("storage_scope") == "editor_session":
            item["scope"] = "editor"
        fields[row["name"]] = item
    return {"mode": _mode(data.get("mode")), "fields": fields}


def for_model(name, result):
    if not result.get("ok"):
        return dict({"ok": False, "error": result.get("error", "操作失败")},
                    **{key: result[key] for key in ("error_code", "path", "expected", "received", "not_executed") if key in result})
    data = result.get("data")
    if isinstance(data, dict):
        if name in MODIFY_TOOLS:
            data = {key: value for key, value in data.items() if key not in ("note", "batch_id", "affected_modes")}
            data["affects"] = [MODE_CODES.get(mode, mode) for mode in result["data"].get("affected_modes", [])]
            if "不随卡" in result["data"].get("note", ""):
                data["scope"] = "editor"
        elif name in ("get_context", "read_card"):
            data = _snapshot(data)
        elif name == "describe_fields":
            data = _description(data)
        elif name in ("switch_mode", "select_card", "open_page"):
            data = {key: data[key] for key in ("card_uid", "card_label", "title", "page") if key in data}
            data["mode"] = _mode(result["data"].get("mode"))
        elif name == "search_cards":
            cards = []
            for card in data.get("cards", []):
                value = {key: value for key, value in card.items() if key not in ("sc_name", "cn_name", "jp_name", "en_name")}
                value["name"] = next((card.get(key) for key in ("sc_name", "cn_name", "jp_name", "en_name") if card.get(key)), "")
                cards.append(value)
            data = {"total": data.get("total"), "cards": cards}
        if name == "run_sandbox_test":
            data["results"] = [{k: v for k, v in r.items() if k not in ("questions", "log", "revision", "scenario_revision")}
                               for r in data.get("results", [])]
            for item, original in zip(data["results"], result["data"].get("results", [])):
                if item.get("status") != "通过":
                    item["recent_log"] = original.get("log", [])[-12:]
        if "verification" in data:
            proof = data["verification"]
            data["verification"] = {k: proof[k] for k in ("passed", "total", "verified", "notice") if k in proof}
            data["verification"]["requirements"] = [{k: row[k] for k in ("effect", "template", "status")} for row in proof.get("requirements", [])]
            data["verification"]["unverified_scenarios"] = [{k: row[k] for k in ("id", "status")} for row in proof.get("unverified_scenarios", [])]
    elif name == "list_modes" and isinstance(data, list):
        data = [row["id"] for row in data]
    return {"ok": True, "data": data}
