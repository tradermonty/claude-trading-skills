# Platformサポート

versioned source of truthは
[`config/platform-compatibility.yaml`](../../config/platform-compatibility.yaml)です。
コントリビューター向けtoolingはCPython `>=3.9,<3.15`を要求し、Linux、Windows、
macOSを認識します。CPython 3.10、3.11、3.12はinstall可能範囲ですが、boundary
matrixで継続実行しないためbest-effortです。PyPy、Python 3.8、Python 3.15以降は
unsupportedで、runtime checkが明確なerrorを返します。

リポジトリルートから次を実行します。

```console
python scripts/check_platform_compatibility.py check
python scripts/check_platform_compatibility.py probe
python scripts/check_platform_compatibility.py validate
```

## 継続検証する行

`pull_request` profileは高速なmerge gateです。schedule実行および手動実行可能な
`nightly` profileは、サポートするboundary/regression matrix全体です。nightlyは
全設定行を含む必要があり、validatorはpolicy driftを拒否します。

| Row ID | Runner | Python | pull_request | nightly | 目的 |
| --- | --- | --- | :---: | :---: | --- |
| `ubuntu-py39` | `ubuntu-latest` | 3.9 | yes | yes | サポートする最小Python |
| `ubuntu-py314` | `ubuntu-latest` | 3.14 | yes | yes | サポートする最新Python |
| `windows-py313` | `windows-latest` | 3.13 | yes | yes | #311を再現するstandalone回帰軸 |
| `windows-py314` | `windows-latest` | 3.14 | no | yes | 最新Windows boundary |
| `macos-py314` | `macos-latest` | 3.14 | no | yes | 最新macOS boundary |

各行はpackage、state、risk、routing、path、encoding、subprocessの重要contractだけを
実行します。動的に検出する全skill suiteはprimaryのUbuntu/Python 3.9軸に残し、
全skillを全OSへ機械的に展開しません。

Windows行には#64/#311の実回帰、つまりmacro-regime MarkdownのUTF-8出力、package
dependency failure、0/6 macro reportをexposure-coachがfail-closedで扱うことを含めます。

## Shellとautomationの境界

- `python scripts/run_all_tests.py`がcross-platformのper-skill test matrix runnerです。
  `scripts/run_all_tests.sh`はPOSIX専用の便利なwrapperです。
- `scripts/run_skill_generation.sh`と`scripts/run_skill_improvement.sh`はguard付きの
  macOS `launchd`専用wrapperです。LinuxまたはWindowsでは
  [スキル自動化クイックスタート](skill-automation.ja.md)のPython orchestratorを使います。
- `run_skill_improvement_loop.py`を直接実行できるのは分離済みのclean checkout内だけです。
  直接実行ではwrapperのcheckout reset、ignored state保持、log/report linkを再現しません。
