# UEFI 构建触发点

这个目录只用来触发 `build-uefi-sheng` workflow（它监听 `xnu/uefi/**`）。
改动这里的文件会让 CI 重新编译 sheng 的 UEFI 固件。

- 想重跑一次编译：往这里加/改一个文件并推送。
- 预计耗时 40-75 分钟（submodule 约 5GB + EDK2 全量编译）。
