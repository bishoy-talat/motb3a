# -*- coding: utf-8 -*-
"""
theme.py
نظام تصميم موحّد للتطبيق (ألوان، خطوط، وأنماط ttk) لإعطاء شكل عصري متّسق.
"""

import tkinter as tk
from tkinter import ttk

COLORS = {
    "bg": "#F3F4F8",              # خلفية النافذة العامة
    "sidebar_bg": "#1E2233",       # خلفية الشريط الجانبي
    "sidebar_text": "#AEB4C7",     # لون نص عناصر الشريط الجانبي غير المختارة
    "sidebar_active_bg": "#4F5DFF",# خلفية العنصر المختار في الشريط الجانبي
    "sidebar_active_text": "#FFFFFF",
    "sidebar_hover": "#2B3050",
    "card_bg": "#FFFFFF",          # خلفية البطاقات
    "card_border": "#E4E7EF",
    "primary": "#4F5DFF",          # اللون الأساسي (بنفسجي-أزرق)
    "primary_hover": "#3D4BF0",
    "primary_light": "#EEF0FF",
    "success": "#16A34A",
    "success_light": "#E9F9EF",
    "danger": "#E11D48",
    "danger_light": "#FDEEF1",
    "warning": "#D97706",
    "warning_light": "#FEF6E7",
    "text_main": "#111827",
    "text_muted": "#6B7280",
    "text_on_primary": "#FFFFFF",
    "divider": "#EBEDF3",
}

FONTS = {
    "h1": ("Segoe UI", 22, "bold"),
    "h2": ("Segoe UI", 15, "bold"),
    "h3": ("Segoe UI", 13, "bold"),
    "body": ("Segoe UI", 12),
    "body_bold": ("Segoe UI", 12, "bold"),
    "small": ("Segoe UI", 10),
    "small_bold": ("Segoe UI", 10, "bold"),
    "sidebar": ("Segoe UI", 13, "bold"),
    "sidebar_icon": ("Segoe UI", 15),
    "verse": ("Segoe UI", 18, "bold"),
    "verse_ref": ("Segoe UI", 12),
}


def setup_styles(root: tk.Tk):
    """يهيّئ كل أنماط ttk المستخدمة في التطبيق. يُستدعى مرة واحدة عند إنشاء النافذة."""
    style = ttk.Style(root)
    style.theme_use("clam")

    # ---- إطارات عامة ----
    style.configure("App.TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["card_bg"])
    style.configure("Sidebar.TFrame", background=COLORS["sidebar_bg"])

    # ---- تسميات ----
    style.configure("H1.TLabel", background=COLORS["bg"], foreground=COLORS["text_main"], font=FONTS["h1"])
    style.configure("H2.TLabel", background=COLORS["card_bg"], foreground=COLORS["text_main"], font=FONTS["h2"])
    style.configure("Body.TLabel", background=COLORS["card_bg"], foreground=COLORS["text_main"], font=FONTS["body"])
    style.configure("BodyOnApp.TLabel", background=COLORS["bg"], foreground=COLORS["text_main"], font=FONTS["body"])
    style.configure("Muted.TLabel", background=COLORS["card_bg"], foreground=COLORS["text_muted"], font=FONTS["small"])
    style.configure("MutedOnApp.TLabel", background=COLORS["bg"], foreground=COLORS["text_muted"], font=FONTS["small"])

    # ---- حقول الإدخال ----
    style.configure("App.TEntry", font=FONTS["body"], padding=6, relief="flat",
                     fieldbackground="#FFFFFF", bordercolor=COLORS["card_border"])
    style.map("App.TEntry", bordercolor=[("focus", COLORS["primary"])])

    # ---- أزرار ----
    style.configure("Primary.TButton", font=FONTS["body_bold"], padding=(16, 9),
                     background=COLORS["primary"], foreground=COLORS["text_on_primary"], borderwidth=0)
    style.map("Primary.TButton", background=[("active", COLORS["primary_hover"]), ("!disabled", COLORS["primary"])])

    style.configure("Secondary.TButton", font=FONTS["body"], padding=(14, 8),
                     background="#E9EBF5", foreground=COLORS["text_main"], borderwidth=0)
    style.map("Secondary.TButton", background=[("active", "#DCDFF0")])

    style.configure("Danger.TButton", font=FONTS["body_bold"], padding=(14, 8),
                     background=COLORS["danger"], foreground="white", borderwidth=0)
    style.map("Danger.TButton", background=[("active", "#C11842")])

    # ---- الجداول (Treeview) ----
    style.configure("App.Treeview", font=FONTS["body"], rowheight=32, borderwidth=0,
                     background="white", fieldbackground="white", foreground=COLORS["text_main"])
    style.configure("App.Treeview.Heading", font=FONTS["small_bold"], background=COLORS["primary"],
                     foreground="white", relief="flat", padding=(8, 8))
    style.map("App.Treeview.Heading", background=[("active", COLORS["primary_hover"])])
    style.map("App.Treeview", background=[("selected", COLORS["primary_light"])],
              foreground=[("selected", COLORS["text_main"])])

    # ---- checkbutton ----
    style.configure("App.TCheckbutton", font=FONTS["body"], background=COLORS["card_bg"],
                     foreground=COLORS["text_main"])

    # ---- قائمة منسدلة (Combobox) ----
    style.configure("App.TCombobox", font=FONTS["body"], padding=6,
                     fieldbackground="#FFFFFF", background="#FFFFFF")
    style.map("App.TCombobox", bordercolor=[("focus", COLORS["primary"])])

    # ---- شريط تمرير ----
    style.configure("App.Vertical.TScrollbar", background=COLORS["bg"], troughcolor=COLORS["bg"],
                     bordercolor=COLORS["bg"], arrowcolor=COLORS["text_muted"])

    return style


def card(parent, **kwargs):
    """يُنشئ إطار 'بطاقة' أبيض بحواف خفيفة يُستخدم كحاوية لكل قسم في الصفحة."""
    outer = tk.Frame(parent, bg=COLORS["card_border"], highlightthickness=0)
    inner = tk.Frame(outer, bg=COLORS["card_bg"], **kwargs)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return outer, inner


def pill_label(parent, text, bg, fg):
    """تسمية على شكل 'وسم/pill' ملوّن - تُستخدم للحالات (تنبيه، نجاح...)."""
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=FONTS["small_bold"],
                     padx=10, pady=4)
