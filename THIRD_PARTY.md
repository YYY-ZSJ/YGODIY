# 第三方资料声明

| 内容 | 位置 | 来源 | 许可 |
| --- | --- | --- | --- |
| Lua 函数说明、常量表、代码片段 | `diy_workbench/lua_intel/` | [DataEditorY](https://github.com/kkr223/DataEditorY) 的 `resources/lua-intel` | MIT（该项目在 `package.json` 中声明，仓库没有单独的 LICENSE 文件） |

对局测试使用 ygopro-core 引擎，引擎文件不包含在本仓库中。

## 独立构建资源

`resources-manifest.json` 记录单独发布的运行资源及其校验值。

| 内容 | 位置 | 来源与授权记录 |
| --- | --- | --- |
| 卡框、图标、默认配置和字体 | 资源包中的 `mold`、`CardBack`、`Field_Center`、`Past_Version`、`Rush_Duel`、`config` | 原程序随附资源，沿用各自权利人的授权 |
| 本地神经翻译模型 | `ygo_translator/model/ygo_nmt_q8.gguf` | 以 [Qwen3-0.6B-Base](https://huggingface.co/Qwen/Qwen3-0.6B-Base) 为基座，经 YGODIY 的 LoRA 微调并转换为 GGUF Q8_0；基座许可为 Apache-2.0，文本见 [Qwen3-LICENSE](licenses/Qwen3-LICENSE) |
| 神经翻译推理库 | `ygo_translator/vendor` | llama-cpp-python 0.3.36 的 CPU 轮子、Jinja2、MarkupSafe、typing_extensions 及本地缓存适配模块；上游许可文件保存在相应 `*.dist-info/licenses` 目录 |
| 实例翻译数据 | `ygo_translator/model/ygo_mt.json.gz` | 基于游戏王卡片多语资料整理，卡片内容的权利归原权利人 |

构建时从 PyPI 安装的第三方 Python 包分别保留其上游许可。仓库的 MIT 协议适用于本项目自主源码，资源、字体和模型的授权按以上来源记录执行。

游戏王（Yu-Gi-Oh!）及相关名称、卡片内容的权利归其权利人所有。本项目与 Konami 没有关联。

## DataEditorY 的 MIT 许可文本

MIT License

Copyright (c) kkr223 and DataEditorY contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
