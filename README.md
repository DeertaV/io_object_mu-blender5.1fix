io_object_mu
==========

## Blender 5.1 port — 0.11.6

本地移植版支持缺失子模型跳过与详细报告、源数据保留、逐零件动画选择和可撤销 NLA 播放。导入默认不播放、不改场景时间设置、不创建旧 Unity 碰撞体。

0.11.1：完整保留源 Empty/Transform 节点，包括无名叶节点及原碰撞组件所在变换节点；默认隐藏辅助显示，不删除层级，不创建碰撞组件。

0.11.2：规范化模型路径、唯一大小写匹配、接受游戏根目录；旧式 mesh 引用失效时只在同 CFG 目录中唯一兜底，多候选不猜测；恢复项单独写入 KSP Model Lookup Report。下一次 craft 导入可重试此前缺失的模型。

0.11.3：模组/ModuleManager/PROP/INTERNAL 查找，UTF-8 配置和无名块保留，精确相对路径与同模组目录迁移，定义歧义诊断；新增重建索引、人工确认替代模型、按游戏库/配置目录隔离并随 .blend 保存的替代规则。详见 [MOD_LOOKUP_0.11.3.md](MOD_LOOKUP_0.11.3.md)。

0.11.4：跳过碰撞专用 MeshFilter 白模并保留变换节点；辅助网格的集合实例显隐修复；贴图准确绑定及内嵌、显式 UV/DDS 映射、透明裁切与法线/颜色/发光预览；支持 Craft 的常用外观变体与 MODEL 换图，增加材质预览按钮。详见 [APPEARANCE_0.11.4.md](APPEARANCE_0.11.4.md)。

0.11.5：按材质功能精简节点、合并相同UV、封装颜色/透明与打包法线运算，整理无重叠布局；新增已有场景的整理与带备份精简按钮，保留源动画与导出元数据。详见 [COMPACT_MATERIALS_0.11.5.md](COMPACT_MATERIALS_0.11.5.md)。

0.11.6：修复独立模型/零件的动画归属与资源列表越界，不同实例可同帧播放；真正的重复先提示而不打开覆盖对话框。详见 [ANIMATION_ISOLATION_0.11.6.md](ANIMATION_ISOLATION_0.11.6.md)。

使用说明与未支持数据清单见 [KSP_0.11.0_GUIDE.md](KSP_0.11.0_GUIDE.md)。下面保留上游历史说明，不代表本地版本的最新实现状态。

## 安装与下载 / Installation

本仓库维护 Blender 5.1 兼容版本，上游项目为 [taniwha/io_object_mu](https://github.com/taniwha/io_object_mu)，沿用 GPL-2.0-or-later 许可。

**最新安装包：[io_object_mu_blender51-0.11.6.zip](https://github.com/DeertaV/io_object_mu-blender5.1fix/raw/master/io_object_mu_blender51-0.11.6.zip)**。

保存场景并退出旧插件所在的 Blender 会话；备份旧插件和偏好后，在 Blender 的 Preferences → Get Extensions → Install from Disk 中选择此 ZIP。不要把 GitHub 的“Download ZIP”源码包当成已构建安装包。

本仓库根目录是扩展源码，可用 Blender 官方 `extension build --source-dir . --output-filepath <安装包路径>` 构建；`tests/`、`docs/` 和仓库 ZIP 不打包进扩展。游戏原始资产、用户场景和本地偏好不随项目发布。

- [更新记录](CHANGELOG.md)
- [测试方法](tests/README.md)
- [完整人工测试清单](docs/TEST_CHECKLIST.md)
- [0.11.6 实测报告与未完成项](docs/TEST_REPORT_0.11.6.md)

Blender addon for importing and exporting KSP .mu files.

NOTE: the import/export functionality is still under heavy development, but
importing is mostly working for static meshes (minus normals and tangents).

mu.py is the main workhorse: it reads and writes .mu files. It is independent
of blender and works with both versions 2 and 3 of python. Some notes on mu.py:
* vectors and quaternions are converted from Unities LHS to Blender's RHS on
load and back again when writing.
* vertex tangents are broken (they are incorrectly treated as quaternions), but
will be preserved if mu.py is used to copy a .mu file. This is a bug.
* mu.py always writes version 5 .mu files.
* it may still break, back up your work.

Further Reading
===============

[There's a wiki](https://github.com/taniwha/io_object_mu/wiki) covering topics
including [installation](https://github.com/taniwha/io_object_mu/wiki/Installation).

The KSP Forum with discussions about this is located here:
* https://forum.kerbalspaceprogram.com/index.php?/topic/40056-12-14-blender-mu-importexport-addon/&

