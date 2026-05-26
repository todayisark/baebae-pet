from __future__ import annotations

DEFAULT_LANGUAGE = "zh"
SUPPORTED_LANGUAGES = {"zh", "en"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "menu.state_preview": "State Preview",
        "menu.size": "Size",
        "menu.import_pet": "Import Pet Pack",
        "menu.open_pet_folder": "Open Pet Folder",
        "menu.export_template": "Export Template Pack",
        "menu.manual": "Manual",
        "menu.settings": "Settings",
        "menu.clear_data": "Clear All Data",
        "menu.quit": "Quit",
        "size.small": "Small",
        "size.medium": "Medium",
        "size.large": "Large",
        "state.idle": "Idle",
        "state.typing": "Typing",
        "state.typing_flow": "Typing Flow",
        "state.sleep": "Sleep",
        "state.meal": "Meal",
        "state.jump": "Jump",
        "state.remind": "Reminder",
        "state.poke": "Poke",
        "state.drag": "Drag",
        "dialog.import_pet_title": "Import Pet Pack",
        "dialog.pet_package_filter": "Pet package (*.zip)",
        "dialog.import_failed_title": "Import Failed",
        "dialog.missing_manifest": "manifest.json was not found in this pet pack.",
        "dialog.import_success_title": "Import Complete",
        "dialog.import_success_message": "Switched to {name}",
        "dialog.open_folder_failed_title": "Open Folder Failed",
        "dialog.open_folder_failed_message": "Could not open pet folder:\n{path}",
        "dialog.export_template_title": "Export Template Pack",
        "dialog.export_success_title": "Export Complete",
        "dialog.export_success_message": "Template pet pack exported:\n{path}",
        "dialog.export_failed_title": "Export Failed",
        "dialog.export_failed_message": "Could not export template pet pack: {error}",
        "dialog.settings_title": "Settings",
        "dialog.settings_general": "General",
        "dialog.settings_language": "Language",
        "dialog.settings_rest": "Break Reminder",
        "dialog.settings_rest_interval": "Interval (minutes)",
        "dialog.settings_rest_message": "Message",
        "dialog.settings_meal": "Meal Reminders",
        "dialog.settings_meal_message": "Message",
        "dialog.meal_enabled": "Enable meal reminders",
        "dialog.meal_breakfast": "Breakfast",
        "dialog.meal_lunch": "Lunch",
        "dialog.meal_dinner": "Dinner",
        "dialog.clear_data_title": "Clear All Data",
        "dialog.clear_data_message": (
            "This will delete all pet packs and settings.\n"
            "The app will quit after clearing data."
        ),
        "reminder.dismiss": "Got it",
    },
    "zh": {
        "menu.state_preview": "状态预览",
        "menu.size": "切换大小",
        "menu.import_pet": "导入素材包",
        "menu.open_pet_folder": "打开素材目录",
        "menu.export_template": "导出模板素材包",
        "menu.manual": "使用手册",
        "menu.settings": "设置",
        "menu.clear_data": "清除所有数据",
        "menu.quit": "退出",
        "size.small": "小",
        "size.medium": "中",
        "size.large": "大",
        "state.idle": "待机",
        "state.typing": "打字",
        "state.typing_flow": "专注打字",
        "state.sleep": "睡觉",
        "state.meal": "吃饭",
        "state.jump": "跳跃",
        "state.remind": "休息提醒",
        "state.poke": "点击回应",
        "state.drag": "拖拽中",
        "dialog.import_pet_title": "导入素材包",
        "dialog.pet_package_filter": "素材包 (*.zip)",
        "dialog.import_failed_title": "导入失败",
        "dialog.missing_manifest": "素材包中没有 manifest.json",
        "dialog.import_success_title": "导入成功",
        "dialog.import_success_message": "已切换到 {name}",
        "dialog.open_folder_failed_title": "打开目录失败",
        "dialog.open_folder_failed_message": "无法打开素材目录：\n{path}",
        "dialog.export_template_title": "导出模板素材包",
        "dialog.export_success_title": "导出成功",
        "dialog.export_success_message": "已导出模板素材包：\n{path}",
        "dialog.export_failed_title": "导出失败",
        "dialog.export_failed_message": "无法导出模板素材包：{error}",
        "dialog.settings_title": "设置",
        "dialog.settings_general": "通用",
        "dialog.settings_language": "语言",
        "dialog.settings_rest": "休息提醒",
        "dialog.settings_rest_interval": "间隔（分钟）",
        "dialog.settings_rest_message": "提示文案",
        "dialog.settings_meal": "吃饭提醒",
        "dialog.settings_meal_message": "提示文案",
        "dialog.meal_enabled": "开启吃饭提醒",
        "dialog.meal_breakfast": "早餐",
        "dialog.meal_lunch": "午餐",
        "dialog.meal_dinner": "晚餐",
        "dialog.clear_data_title": "清除所有数据",
        "dialog.clear_data_message": "这将删除所有素材包和设置，确认吗？\n（程序将退出）",
        "reminder.dismiss": "我知道了",
    },
}


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


def t(key: str, language: str | None, **kwargs: object) -> str:
    normalized = normalize_language(language)
    text = TRANSLATIONS[normalized].get(key) or TRANSLATIONS[DEFAULT_LANGUAGE][key]
    if kwargs:
        return text.format(**kwargs)
    return text
