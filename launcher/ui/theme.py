# -*- coding: utf-8 -*-
"""PCL CE 风格主题：参数化 QSS（主题色可自定义）、圆角卡片、柔和阴影。"""
import colorsys

from PyQt5.QtGui import QColor

DEFAULT_ACCENT = "#4A8F72"

PRESET_COLORS = [
    "#4A8F72",  # 苔绿（默认）
    "#3B82F6",  # 晴空蓝
    "#6366F1",  # 靛蓝
    "#8B5CF6",  # 紫罗兰
    "#EC4899",  # 樱粉
    "#F59E0B",  # 琥珀
    "#EF4444",  # 珊瑚红
    "#10B981",  # 翠绿
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


def build_qss(accent: str = DEFAULT_ACCENT) -> str:
    """生成全局 QSS。视觉基准：PCL CE —— 左侧导航胶囊高亮、圆角卡片、柔边框。"""
    a_light = accent_light(accent)
    a_dark = accent_dark(accent)
    a_soft = accent_soft(accent)
    return f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    outline: none;
}}
QMainWindow, QDialog {{
    background: #F4F6F8;
}}
QWidget#navPanel {{
    background: #FFFFFF;
    border-right: 1px solid #E5E9EF;
}}
QLabel#navTitle {{
    color: #1F2328;
    font-size: 15px;
    font-weight: 600;
    padding: 6px 4px 2px 4px;
}}
QLabel#navSubtitle {{
    color: #6B7280;
    font-size: 11px;
    padding: 0 4px;
}}
QPushButton#navBtn {{
    color: #4B5563;
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 11px 14px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#navBtn:hover {{
    background: #EEF1F5;
    color: #1F2328;
}}
QPushButton#navBtn:checked {{
    background: {a_soft};
    color: {a_dark};
    font-weight: 600;
}}
QFrame#card {{
    background: #FFFFFF;
    border: 1px solid #E5E9EF;
    border-radius: 12px;
}}
QLabel#cardTitle {{
    color: #1F2328;
    font-size: 13px;
    font-weight: 600;
}}
QLabel#subText {{
    color: #6B7280;
    font-size: 12px;
}}
QLabel#heroVersion {{
    color: #1F2328;
    font-size: 20px;
    font-weight: 700;
}}
QLabel#accentText {{
    color: {a_dark};
    font-weight: 600;
}}
QPushButton {{
    background: #FFFFFF;
    color: #1F2328;
    border: 1px solid #D8DEE6;
    border-radius: 9px;
    padding: 8px 16px;
    font-size: 13px;
}}
QPushButton:hover {{
    border-color: {a_light};
    color: {a_dark};
}}
QPushButton:pressed {{
    background: #F0F3F7;
}}
QPushButton:disabled {{
    color: #9CA3AF;
    background: #F3F4F6;
    border-color: #E5E7EB;
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
    background: #C4CCD4;
    color: #F3F4F6;
}}
QPushButton#bigLaunch {{
    background: {accent};
    color: #FFFFFF;
    border: none;
    border-radius: 14px;
    font-size: 17px;
    font-weight: 700;
    padding: 18px 24px;
}}
QPushButton#bigLaunch:hover {{
    background: {a_light};
}}
QPushButton#bigLaunch:pressed {{
    background: {a_dark};
}}
QPushButton#bigLaunch:disabled {{
    background: #C4CCD4;
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
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: #FFFFFF;
    border: 1px solid #D8DEE6;
    border-radius: 9px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: {a_light};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
}}
QComboBox {{
    background: #FFFFFF;
    border: 1px solid #D8DEE6;
    border-radius: 9px;
    padding: 7px 10px;
    font-size: 13px;
}}
QComboBox:hover {{
    border-color: {a_light};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: #FFFFFF;
    border: 1px solid #E5E9EF;
    border-radius: 9px;
    selection-background-color: {a_soft};
    selection-color: {a_dark};
    outline: none;
}}
QListWidget {{
    background: #FFFFFF;
    border: 1px solid #E5E9EF;
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    border-radius: 8px;
    padding: 8px 10px;
    margin: 1px 2px;
    color: #1F2328;
}}
QListWidget::item:hover {{
    background: #EEF1F5;
}}
QListWidget::item:selected {{
    background: {a_soft};
    color: {a_dark};
    font-weight: 600;
}}
QProgressBar {{
    background: #EDF0F4;
    border: none;
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: #374151;
    font-size: 11px;
    font-weight: 600;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 8px;
}}
QPlainTextEdit#logView {{
    background: #FBFCFD;
    border: 1px solid #E5E9EF;
    border-radius: 10px;
    color: #374151;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 12px;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: #E2E7EE;
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
    color: #374151;
    spacing: 7px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid #C9D1DB;
    border-radius: 5px;
    background: #FFFFFF;
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #C9D1DB;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #AAB4C0;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #C9D1DB;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QMessageBox {{
    background: #FFFFFF;
}}
QMessageBox QLabel {{
    color: #1F2328;
    font-size: 13px;
}}
QToolTip {{
    background: #1F2328;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 12px;
}}
"""
