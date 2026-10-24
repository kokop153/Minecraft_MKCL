# -*- coding: utf-8 -*-
"""PCL CE 风格主题：参数化 QSS（主题色 + 明/暗模式）、圆角卡片、蓝色顶栏、玻璃浮层。"""
import colorsys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QColor, QIcon, QPainter, QPixmap, QFont, QFontInfo, QFontMetrics,
    QPalette,
)
from PyQt5.QtWidgets import QLabel

DEFAULT_ACCENT = "#4C5FE8"   # PCL CE 同款蓝
LEGACY_DEFAULT_ACCENT = "#4C5FE8"  # 旧版默认（迁移用）

PRESET_COLORS = [
    "#4C5FE8",  # PCL 蓝（默认）
    "#3B82F6",  # 晴空蓝
    "#6366F1",  # 靛蓝
    "#8B5CF6",  # 紫罗兰
    "#48C6EC",  # 天青
    "#F59E0B",  # 琥珀
    "#8583F3",  # 珊瑚紫
    "#10A0B9",  # 浅青
    "#4A8F72",  # 苔绿
]


def _shift(hex_color: str, sat: float, val: float) -> str:
    c = QColor(hex_color)
    h, s, v, _ = c.getHsvF()
    if h < 0:
        h, s, v = 0.0, 0.0, 1.0
    return QColor.fromHsvF(
        h, max(0.0, min(1.0, s * sat)), max(0.0, min(1.0, v * val))
    ).name()


def accent_light(hex_color: str) -> str:
    return _shift(hex_color, 0.6, 1.25)


def accent_dark(hex_color: str) -> str:
    return _shift(hex_color, 1.05, 0.82)


def accent_soft(hex_color: str) -> str:
    """极浅主题色底（卡片高亮、选中态）。"""
    c = QColor(hex_color)
    h, s, v, _ = c.getHsvF()
    if h < 0:
        h = 0.0
    return QColor.fromHsvF(h, max(0.10, s * 0.35), 0.965).name()


def glyph_icon(glyph: str, color: str = "#FFFFFF", size: int = 14) -> QIcon:
    """用 Segoe MDL2 Assets 字体把字形渲染成图标（Windows 10+ 自带）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    font = None
    for family in ("Segoe MDL2 Assets", "Segoe Fluent Icons", "Segoe UI Symbol"):
        f = QFont(family)
        if QFontInfo(f).family() == family:
            font = f
            break
    if font is None:
        font = QFont()
    font.setPixelSize(max(9, int(size * 0.9)))
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignCenter, glyph)
    p.end()
    return QIcon(pm)


# MDL2 常用字形
GLYPHS = {
    "home": "\uE768",        # Play
    "versions": "\uE71D",    # AllApps
    "downloads": "\uE896",   # Download
    "process": "\uE9D9",     # Diagnostic
    "settings": "\uE713",    # Setting
    "minimize": "\uE921",    # ChromeMinimize
    "close": "\uE8BB",       # ChromeClose
}


class ElideLabel(QLabel):
    """单行省略标签：文字按当前宽度中间省略，悬停显示全文。

    普通 QLabel 即使开了 wordWrap，minimumSizeHint 仍按不换行的全文宽计算，
    长路径 / 命令行会把布局最小宽度顶到几千像素、进而把窗口撑爆
    （Qt 已知行为）。此类从根源上避免「内容顶大窗口」。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(False)
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        super().setText(self._elide(self._full_text))

    def setText(self, text):
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        super().setText(self._elide(self._full_text))

    def _elide(self, text):
        return QFontMetrics(self.font()).elidedText(
            text, Qt.ElideMiddle, max(40, self.width() - 4))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._full_text:
            super().setText(self._elide(self._full_text))


def _dark_palette(accent: str) -> dict:
    return {
        "window": "#161920",
        "card": "#1F232C",
        "card_border": "#2E3440",
        "text": "#E6E9F0",
        "text_strong": "#F2F4F8",
        "sub": "#98A2B3",
        "input_bg": "#1A1E26",
        "input_border": "#3A4150",
        "hover_bg": "#262C37",
        "pressed_bg": "#20252F",
        "list_hover": "#262C37",
        "selected_bg": accent_dark(accent),
        "selected_text": "#FFFFFF",
        "progress_track": "#2A303B",
        "progress_text": "#C9CFDA",
        "log_bg": "#14171E",
        "log_border": "#2E3440",
        "log_text": "#C7CDD8",
        "btn_border": "#454D5C",
        "btn_disabled_bg": "#232833",
        "btn_disabled_text": "#6B7280",
        "btn_disabled_border": "#333A46",
        "slider_groove": "#2E3440",
        "scroll_handle": "#4A5361",
        "scroll_handle_hover": "#5D6775",
        "check_border": "#555E6E",
        "check_bg": "#1A1E26",
    }


def _light_palette(accent: str) -> dict:
    return {
        "window": "#F4F6F8",
        "card": "#FFFFFF",
        "card_border": "#E5E9EF",
        "text": "#1F2328",
        "text_strong": "#1F2328",
        "sub": "#6B7280",
        "input_bg": "#FFFFFF",
        "input_border": "#D8DEE6",
        "hover_bg": "#EEF1F5",
        "pressed_bg": "#F0F3F7",
        "list_hover": "#EEF1F5",
        "selected_bg": accent_soft(accent),
        "selected_text": accent_dark(accent),
        "progress_track": "#EDF0F4",
        "progress_text": "#374151",
        "log_bg": "#FBFCFD",
        "log_border": "#E5E9EF",
        "log_text": "#374151",
        "btn_border": "#D8DEE6",
        "btn_disabled_bg": "#F3F4F6",
        "btn_disabled_text": "#9CA3AF",
        "btn_disabled_border": "#E5E7EB",
        "slider_groove": "#E2E7EE",
        "scroll_handle": "#C9D1DB",
        "scroll_handle_hover": "#AAB4C0",
        "check_border": "#C9D1DB",
        "check_bg": "#FFFFFF",
    }


def build_qss(accent: str = DEFAULT_ACCENT, dark: bool = False) -> str:
    """生成全局 QSS。视觉基准：PCL CE —— 蓝色顶栏 + 居中白色胶囊导航 + 圆角卡片。"""
    a_light = accent_light(accent)
    a_dark = accent_dark(accent)
    a_soft = accent_soft(accent)
    p = _dark_palette(accent) if dark else _light_palette(accent)
    if dark:
        glass = {
            "bg": "rgba(17,21,30,172)", "border": "rgba(255,255,255,28)",
            "text": "rgba(255,255,255,0.92)", "sub": "rgba(255,255,255,0.55)",
            "title": "#FFFFFF", "inset": "transparent",
            "log_text": "rgba(255,255,255,0.85)",
            "track": "rgba(255,255,255,0.16)",
            "spin_bg": "rgba(255,255,255,0.12)", "spin_text": "#FFFFFF",
            "spin_border": "rgba(255,255,255,0.35)",
            "btn_bg": "rgba(255,255,255,0.12)", "btn_text": "#FFFFFF",
            "btn_border": "rgba(255,255,255,0.35)", "btn_hover": "rgba(255,255,255,0.20)",
            "greet": "#FFFFFF", "greet_sub": "rgba(255,255,255,0.55)",
        }
    else:
        glass = {
            "bg": "rgba(255,255,255,168)", "border": "rgba(255,255,255,150)",
            "text": "#2A2F3A", "sub": "#6B7280",
            "title": "#1F2328", "inset": "rgba(255,255,255,0.55)",
            "log_text": "#374151",
            "track": "rgba(15,20,30,0.10)",
            "spin_bg": "rgba(255,255,255,0.85)", "spin_text": "#1F2328",
            "spin_border": "#D8DEE6",
            "btn_bg": "#FFFFFF", "btn_text": "#374151",
            "btn_border": "#D8DEE6", "btn_hover": "#F0F3F7",
            "greet": "#1F2328", "greet_sub": "#6B7280",
        }
    return f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    outline: none;
}}
QMainWindow, QDialog {{
    background: {p['window']};
}}
QWidget#central {{ background: {p['window']}; }}

/* ---------- 通用文字色（未单独命名的 QLabel 必须跟随明暗，否则暗黑下为黑字） ---------- */
QLabel {{
    color: {p['text']};
    background: transparent;
}}

/* ---------- 顶部蓝色标题栏（PCL CE 风格） ---------- */
QFrame#topBar {{
    background: {accent};
    border: none;
}}
QLabel#topTitle {{
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 600;
    background: transparent;
}}
QLabel#topBadge {{
    color: {accent};
    background: #FFFFFF;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
}}
QPushButton#navPill {{
    color: rgba(255,255,255,0.88);
    background: transparent;
    border: none;
    border-radius: 15px;
    padding: 6px 15px;
    font-size: 13px;
}}
QPushButton#navPill:hover {{
    background: rgba(255,255,255,0.16);
    color: #FFFFFF;
}}
QPushButton#navPill:checked {{
    background: #FFFFFF;
    color: {a_dark};
    font-weight: 600;
}}
QPushButton#winBtn {{
    color: rgba(255,255,255,0.9);
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px 10px;
    font-size: 12px;
}}
QPushButton#winBtn:hover {{
    background: rgba(255,255,255,0.22);
    color: #FFFFFF;
}}
QPushButton#closeBtn:hover {{
    background: #E81123;
    color: #FFFFFF;
}}

/* ---------- 主页（PCL 式浮层） ---------- */
QWidget#sidePanel {{
    background: rgba(17,21,30,158);
}}
QPushButton#avatarBtn {{
    background: rgba(255,255,255,0.16);
    color: #FFFFFF;
    border: 2px solid rgba(255,255,255,0.28);
    border-radius: 33px;
    font-size: 25px;
    font-weight: 700;
}}
QPushButton#avatarBtn:hover {{
    background: rgba(255,255,255,0.28);
}}
QLabel#sideName {{
    color: #FFFFFF;
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}}
QLabel#sideSub {{
    color: rgba(255,255,255,0.55);
    font-size: 11px;
    background: transparent;
}}
QPushButton#sideGhost {{
    color: rgba(255,255,255,0.92);
    background: transparent;
    border: none;
    font-size: 15px;
    font-weight: 600;
    padding: 2px 6px;
}}
QPushButton#sideGhost:hover {{
    color: #FFFFFF;
    text-decoration: underline;
}}
QLabel#launchTitle {{
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 700;
    background: transparent;
}}
QLabel#launchSub {{
    color: rgba(255,255,255,0.72);
    font-size: 11px;
    background: transparent;
}}
QFrame#glassCard {{
    background: {glass['bg']};
    border: 1px solid {glass['border']};
    border-radius: 14px;
}}
QFrame#glassCard QLabel {{
    color: {glass['text']};
    background: transparent;
}}
QFrame#glassCard QLabel#subText {{
    color: {glass['sub']};
}}
QFrame#glassCard QLabel#cardTitle {{
    color: {glass['title']};
}}
QLabel#heroGreet {{
    color: {glass['greet']};
    font-size: 19px;
    font-weight: 700;
    background: transparent;
}}
QLabel#heroGreetSub {{
    color: {glass['greet_sub']};
    font-size: 12px;
    background: transparent;
}}
QFrame#glassCard QProgressBar {{
    background: {glass['track']};
    border: none;
    border-radius: 8px;
    height: 14px;
    text-align: center;
    color: {glass['text']};
    font-size: 11px;
    font-weight: 600;
}}
QFrame#glassCard QProgressBar::chunk {{
    background: {accent};
    border-radius: 7px;
}}
QFrame#glassCard QSpinBox {{
    background: {glass['spin_bg']};
    color: {glass['spin_text']};
    border: 1px solid {glass['spin_border']};
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 12px;
}}
QFrame#glassCard QPlainTextEdit#homeLog {{
    background: {glass['inset']};
    color: {glass['log_text']};
    border: none;
    border-radius: 10px;
    padding: 6px 8px;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 12px;
}}
QFrame#glassCard QScrollBar::handle:vertical {{
    background: rgba(120,130,150,0.45);
}}
QFrame#glassCard QScrollBar::handle:vertical:hover {{
    background: rgba(120,130,150,0.65);
}}
QPushButton#glassBtn {{
    background: {glass['btn_bg']};
    color: {glass['btn_text']};
    border: 1px solid {glass['btn_border']};
    border-radius: 9px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#glassBtn:hover {{
    background: {glass['btn_hover']};
}}

/* ---------- 半透明描边按钮（主页侧栏用，恒为深色底） ---------- */
QPushButton#outlineBtn {{
    background: transparent;
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.72);
    border-radius: 10px;
    padding: 9px 14px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#outlineBtn:hover {{
    background: rgba(255,255,255,0.14);
    border-color: #FFFFFF;
}}
QPushButton#outlineBtn:pressed {{
    background: rgba(255,255,255,0.24);
}}
QPushButton#outlineBtn:disabled {{
    color: rgba(255,255,255,0.35);
    border-color: rgba(255,255,255,0.25);
    background: transparent;
}}
QPushButton#bigLaunch {{
    background: transparent;
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.85);
    border-radius: 12px;
    font-size: 16px;
    font-weight: 700;
    padding: 12px 18px;
}}
QPushButton#bigLaunch:hover {{
    background: rgba(255,255,255,0.14);
    border-color: #FFFFFF;
}}
QPushButton#bigLaunch:pressed {{
    background: rgba(255,255,255,0.24);
}}
QPushButton#bigLaunch:disabled {{
    color: rgba(255,255,255,0.35);
    border-color: rgba(255,255,255,0.25);
}}

/* ---------- 通用控件 ---------- */
QFrame#card {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    border-radius: 12px;
}}
QLabel#cardTitle {{
    color: {p['text_strong']};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#subText {{
    color: {p['sub']};
    font-size: 12px;
}}
QLabel#heroVersion {{
    color: {p['text_strong']};
    font-size: 20px;
    font-weight: 700;
}}
QLabel#accentText {{
    color: {a_dark};
    font-weight: 600;
}}
QPushButton {{
    background: {p['card']};
    color: {p['text']};
    border: 1px solid {p['btn_border']};
    border-radius: 9px;
    padding: 8px 16px;
    font-size: 13px;
}}
QPushButton:hover {{
    border-color: {a_light};
    color: {a_dark};
}}
QPushButton:pressed {{
    background: {p['pressed_bg']};
}}
QPushButton:disabled {{
    color: {p['btn_disabled_text']};
    background: {p['btn_disabled_bg']};
    border-color: {p['btn_disabled_border']};
}}
QPushButton#primaryBtn {{
    background: {accent};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton#primaryBtn:hover {{
    background: {a_light};
}}
QPushButton#primaryBtn:pressed {{
    background: {a_dark};
}}
QPushButton#primaryBtn:disabled {{
    background: {p['btn_disabled_bg']};
    color: {p['btn_disabled_text']};
}}
QPushButton#sideBtn {{
    background: {a_soft};
    color: {a_dark};
    border: none;
    border-radius: 10px;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
}}
QPushButton#sideBtn:hover {{
    background: {a_light};
}}
/* 下载页分段控件（客户端 / 模组 / 整合包） */
QFrame#seg {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    border-radius: 10px;
}}
QPushButton#segBtn {{
    color: {p['text']};
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 7px 18px;
    font-size: 13px;
}}
QPushButton#segBtn:hover {{
    color: {a_dark};
}}
QPushButton#segBtn:checked {{
    background: {accent};
    color: #FFFFFF;
    font-weight: 600;
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1px solid {p['input_border']};
    border-radius: 5px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: {a_light};
    selection-color: {p['selected_text']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
}}
/* SpinBox 上下箭头：用户要求数字框不要箭头，直接隐藏按钮区；
   数值仍可用滚轮 / 键盘上下键调整 */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QComboBox {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1px solid {p['input_border']};
    border-radius: 5px;
    padding: 7px 10px;
    font-size: 13px;
}}
QComboBox:hover {{
    border-color: {a_light};
}}
QComboBox QAbstractItemView {{
    background: {p['card']};
    color: {p['text']};
    border: 1px solid {p['card_border']};
    border-radius: 6px;
    selection-background-color: {p['selected_bg']};
    selection-color: {p['selected_text']};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 6px;
    color: {p['text']};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {p['selected_bg']};
    color: {p['selected_text']};
}}
QListWidget {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1px solid {p['card_border']};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    border-radius: 8px;
    padding: 8px 10px;
    margin: 1px 2px;
    color: {p['text']};
}}
QListWidget::item:hover {{
    background: {p['list_hover']};
}}
QListWidget::item:selected {{
    background: {p['selected_bg']};
    color: {p['selected_text']};
    font-weight: 600;
}}
/* ---------- 进程表格（QTableWidget，替代原生 Windows 样式） ---------- */
QTableWidget {{
    background: {p['input_bg']};
    alternate-background-color: {p['hover_bg']};
    color: {p['text']};
    border: none;
    border-radius: 10px;
    gridline-color: transparent;
    outline: none;
    selection-background-color: {p['selected_bg']};
    selection-color: {p['selected_text']};
}}
QTableWidget::item {{
    border: none;
    padding: 5px 4px;
}}
QTableWidget::item:hover {{
    background: {p['list_hover']};
}}
QTableWidget::item:selected {{
    background: {p['selected_bg']};
    color: {p['selected_text']};
}}
QHeaderView::section {{
    background: {p['card']};
    color: {p['sub']};
    border: none;
    border-bottom: 1px solid {p['card_border']};
    padding: 8px 9px;
    font-size: 12px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {p['card']};
    border: none;
    border-bottom: 1px solid {p['card_border']};
}}
QProgressBar {{
    background: {p['progress_track']};
    border: none;
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: {p['progress_text']};
    font-size: 11px;
    font-weight: 600;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 8px;
}}
QPlainTextEdit#logView {{
    background: {p['log_bg']};
    border: 1px solid {p['log_border']};
    border-radius: 10px;
    color: {p['log_text']};
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 12px;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {p['slider_groove']};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #FFFFFF;
    border: 2px solid {accent};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    border-color: {a_light};
}}
QCheckBox {{
    color: {p['text']};
    spacing: 7px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {p['check_border']};
    border-radius: 5px;
    background: {p['check_bg']};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: none;
}}
QRadioButton {{
    color: {p['text']};
    spacing: 8px;
    font-size: 13px;
}}
QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {p['check_border']};
    border-radius: 8px;
    background: {p['check_bg']};
}}
QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}
QLabel#groupHeader {{
    color: {p['sub']};
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    background: transparent;
}}
QFrame#settingsNav {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    border-radius: 12px;
}}
QPushButton#settingsNavBtn {{
    color: {p['text']};
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#settingsNavBtn:hover {{
    background: {p['hover_bg']};
}}
QPushButton#settingsNavBtn:checked {{
    background: {a_soft};
    color: {a_dark};
    font-weight: 600;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p['scroll_handle']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p['scroll_handle_hover']};
}}
/* 滚动条：保持可见（不用滚轮替换），去掉上下箭头（add-line/sub-line 收为零） */
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
    background: transparent;
    image: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p['scroll_handle']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    border: none;
    background: transparent;
    image: none;
}}
QMessageBox {{
    background: {p['card']};
}}
QMessageBox QLabel {{
    color: {p['text']};
    font-size: 13px;
}}
QToolTip {{
    background: {p['card']};
    color: {p['text']};
    border: 1px solid {p['card_border']};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 12px;
}}
"""


def current_palette(accent: str, dark: bool) -> dict:
    """按主题取调色板 dict（build_qss 内部同源）。"""
    return _dark_palette(accent) if dark else _light_palette(accent)


def combo_popup_qss(p: dict) -> str:
    """QComboBox 弹出列表的内联 QSS（widget 级，100% 生效）。

    应用级样式表对 Qt.Popup 顶层窗口的传播在部分平台/版本不可靠
    （表现为弹出列表掉回原生白底「白框」）。内联样式表直接设置在
    view 上，与 parent 链无关；且会作用于 view 的子控件（item、
    内部滚动条），主题切换时由 apply_theme 刷新。
    """
    return (
        "QListView {{ background: {bg}; color: {fg};"
        " border: 1px solid {bd}; border-radius: 6px; outline: none; }}"
        "QListView::item {{ padding: 6px 10px; border-radius: 6px;"
        " color: {fg}; }}"
        "QListView::item:hover {{ background: {hover}; }}"
        "QListView::item:selected {{ background: {sel}; color: {selfg}; }}"
        "QScrollBar:vertical {{ background: transparent; width: 9px;"
        " margin: 2px; }}"
        "QScrollBar::handle:vertical {{ background: {sh};"
        " border-radius: 4px; min-height: 30px; }}"
        "QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0;"
        " border: none; background: transparent; image: none; }}"
    ).format(
        bg=p["card"], fg=p["text"], bd=p["card_border"], hover=p["hover_bg"],
        sel=p["selected_bg"], selfg=p["selected_text"], sh=p["scroll_handle"],
    )


def style_combo_popup(combo, p: dict) -> None:
    """给 QComboBox 的弹出视图与外框容器打内联样式，消除原生白框。"""
    try:
        view = combo.view()
    except Exception:
        return
    if view is None:
        return
    view.setStyleSheet(combo_popup_qss(p))
    # QComboBox 的 popup 由 QComboBoxDelegate 绘制，选中项背景走
    # palette.Highlight 而非 QSS 的 ::item:selected——直接把 palette
    # 改写成主题色，双保险（QSS 负责普通项/滚动条，palette 负责选中项）
    pal = view.palette()
    pal.setColor(QPalette.Highlight, QColor(p["selected_bg"]))
    pal.setColor(QPalette.HighlightedText, QColor(p["selected_text"]))
    pal.setColor(QPalette.Text, QColor(p["text"]))
    pal.setColor(QPalette.Base, QColor(p["card"]))
    view.setPalette(pal)
    container = view.parent()
    if container is not None:
        # 外框容器（QComboBoxPrivateContainer）没人管时会露原生白底，
        # 用 card 底 + 同圆角兜底；边框交给 view 画，避免双线
        container.setStyleSheet(
            "background: %s; border-radius: 6px;" % p["card"])
