# -*- coding: utf-8 -*-
"""
main.py
برنامج متابعة المخدومين - نسخة سطح مكتب (Python + Tkinter + SQLite)
تصميم عصري: شريط جانبي للتنقل + بطاقات لكل قسم.

الأقسام:
  1. المخدومين      : إضافة/تعديل/حذف بيانات المخدومين
  2. الحضور والغياب : تسجيل حضور اليوم + تنبيه بمن يحتاج افتقاد
  3. أعياد الميلاد   : عرض أعياد الميلاد القادمة خلال أسبوع
  4. الآية اليومية   : عرض آية اليوم + إدارة بنك الآيات
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import date
import os

import api_client as db
from api_client import ApiError, SessionExpired
from theme import COLORS, FONTS, setup_styles, card, pill_label


NAV_ITEMS_ALL = [
    ("dashboard", "🏠", "الرئيسية"),
    ("students", "👥", "المخدومين"),
    ("stages", "🏷️", "المراحل"),
    ("attendance", "📋", "الحضور والغياب"),
    ("birthdays", "🎂", "أعياد الميلاد"),
    ("reports", "📊", "التقارير والإحصائيات"),
    ("lessons", "🗓️", "الخطة السنوية"),
    ("verse", "📖", "الآية اليومية"),
    ("activity_log", "🕒", "سجل النشاط"),  # أدمن فقط
    ("users", "🔑", "المستخدمين"),  # أدمن فقط
]

ADMIN_ONLY_PAGES = {"stages", "users", "activity_log"}

TAG_COLORS = {
    "يحتاج متابعة خاصة": ("#FDEEF1", "#E11D48"),
    "منتظم جدًا": ("#E9F9EF", "#16A34A"),
    "جديد بالخدمة": ("#EEF2FF", "#4F5DFF"),
}


def format_phone_for_whatsapp(phone):
    """يحوّل رقم مصري محلي (01xxxxxxxxx) إلى صيغة دولية لواتساب (20xxxxxxxxx)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "20" + digits[1:]
    elif not digits.startswith("20") and len(digits) == 11:
        digits = "20" + digits[1:] if digits.startswith("0") else digits
    return digits


def open_whatsapp(phone, message=""):
    import webbrowser
    from urllib.parse import quote

    number = format_phone_for_whatsapp(phone)
    if not number:
        messagebox.showwarning("تنبيه", "لا يوجد رقم هاتف صحيح لهذا المخدوم")
        return
    url = f"https://wa.me/{number}"
    if message:
        url += f"?text={quote(message)}"
    webbrowser.open(url)


def get_stage_choices(include_all=True, include_unset=True):
    """
    يرجع قائمة اختيارات المراحل لاستخدامها في القوائم المنسدلة:
    [(النص المعروض, stage_id أو None لكل المراحل أو 'unset' لبدون مرحلة), ...]
    """
    stages = db.get_all_stages()
    choices = []
    if include_all:
        choices.append(("كل المراحل", None))
    for s in stages:
        choices.append((s["name"], s["id"]))
    if include_unset:
        choices.append(("بدون مرحلة", "unset"))
    return choices


# =========================================================
# الشريط الجانبي
# =========================================================
class Sidebar(tk.Frame):
    def __init__(self, parent, on_select, nav_items, user_label=""):
        super().__init__(parent, bg=COLORS["sidebar_bg"], width=230)
        self.pack_propagate(False)
        self.on_select = on_select
        self.buttons = {}
        self.active_key = None
        self.nav_items = nav_items

        # شعار/عنوان أعلى الشريط
        logo_frame = tk.Frame(self, bg=COLORS["sidebar_bg"])
        logo_frame.pack(fill="x", pady=(24, 14), padx=18)
        tk.Label(logo_frame, text="⛪", font=("Segoe UI", 26), bg=COLORS["sidebar_bg"],
                 fg=COLORS["sidebar_active_text"]).pack(anchor="e")
        tk.Label(logo_frame, text="متابعة المخدومين", font=FONTS["h3"],
                 bg=COLORS["sidebar_bg"], fg=COLORS["sidebar_active_text"],
                 wraplength=190, justify="right").pack(anchor="e", pady=(6, 0))
        if user_label:
            tk.Label(logo_frame, text=user_label, font=FONTS["small"],
                     bg=COLORS["sidebar_bg"], fg=COLORS["sidebar_text"],
                     wraplength=190, justify="right").pack(anchor="e", pady=(2, 0))

        tk.Frame(self, bg=COLORS["sidebar_hover"], height=1).pack(fill="x", padx=18, pady=(0, 10))

        # عناصر التنقل
        for key, icon, label in self.nav_items:
            btn = self._make_nav_button(key, icon, label)
            btn.pack(fill="x", padx=12, pady=3)
            self.buttons[key] = btn

        # تذييل بسيط
        tk.Label(self, text="© خدمة المدارس", font=FONTS["small"],
                 bg=COLORS["sidebar_bg"], fg=COLORS["sidebar_text"]).pack(side="bottom", pady=16)

    def _make_nav_button(self, key, icon, label):
        btn = tk.Label(self, text=f"{icon}   {label}", font=FONTS["sidebar"],
                        bg=COLORS["sidebar_bg"], fg=COLORS["sidebar_text"],
                        anchor="e", padx=14, pady=12, cursor="hand2")

        def enter(_e):
            if self.active_key != key:
                btn.config(bg=COLORS["sidebar_hover"])

        def leave(_e):
            if self.active_key != key:
                btn.config(bg=COLORS["sidebar_bg"])

        def click(_e):
            self.set_active(key)
            self.on_select(key)

        btn.bind("<Enter>", enter)
        btn.bind("<Leave>", leave)
        btn.bind("<Button-1>", click)
        return btn

    def set_active(self, key):
        self.active_key = key
        for k, b in self.buttons.items():
            if k == key:
                b.config(bg=COLORS["sidebar_active_bg"], fg=COLORS["sidebar_active_text"])
            else:
                b.config(bg=COLORS["sidebar_bg"], fg=COLORS["sidebar_text"])


# =========================================================
# رأس الصفحة (عنوان + وصف مختصر)
# =========================================================
def page_header(parent, title, subtitle=""):
    header = tk.Frame(parent, bg=COLORS["bg"])
    header.pack(fill="x", padx=28, pady=(24, 10))
    tk.Label(header, text=title, font=FONTS["h1"], bg=COLORS["bg"],
              fg=COLORS["text_main"]).pack(anchor="e")
    if subtitle:
        tk.Label(header, text=subtitle, font=FONTS["small"], bg=COLORS["bg"],
                  fg=COLORS["text_muted"]).pack(anchor="e", pady=(4, 0))
    return header


# =========================================================
# التطبيق الرئيسي
# =========================================================
class MokhdomeenApp(tk.Tk):
    def __init__(self, current_user):
        super().__init__()
        self.current_user = current_user  # sqlite3.Row: username, role, stage_id, stage_name, class_name
        self.is_admin = current_user["role"] == "admin"
        # المرحلة والفصل المقفولين للخادم غير الأدمن (None يعني بلا قفل)
        self.locked_stage_id = None if self.is_admin else current_user["stage_id"]
        self.locked_class_name = None if self.is_admin else current_user["class_name"]

        self.title("برنامج متابعة المخدومين")
        self.geometry("1150x720")
        self.minsize(980, 620)
        self.configure(bg=COLORS["bg"])
        setup_styles(self)

        root = tk.Frame(self, bg=COLORS["bg"])
        root.pack(fill="both", expand=True)

        nav_items = [item for item in NAV_ITEMS_ALL if self.is_admin or item[0] not in ADMIN_ONLY_PAGES]
        role_desc = "أدمن" if self.is_admin else f'خادم ({current_user["stage_name"] or "بدون مرحلة"}'
        if not self.is_admin and current_user["class_name"]:
            role_desc += f' - {current_user["class_name"]}'
        if not self.is_admin:
            role_desc += ")"
        role_label = f'{current_user["username"]} — {role_desc}'

        self.sidebar = Sidebar(root, on_select=self.show_page, nav_items=nav_items, user_label=role_label)
        self.sidebar.pack(side="right", fill="y")

        self.content = tk.Frame(root, bg=COLORS["bg"])
        self.content.pack(side="right", fill="both", expand=True)

        username = current_user["username"]

        self.pages = {
            "dashboard": DashboardPage(self.content, locked_stage_id=self.locked_stage_id,
                                        locked_class_name=self.locked_class_name, go_to_page=self.show_page),
            "students": StudentsPage(self.content, locked_stage_id=self.locked_stage_id,
                                       locked_class_name=self.locked_class_name, username=username),
            "attendance": AttendancePage(self.content, refresh_callback=self.refresh_all,
                                          locked_stage_id=self.locked_stage_id,
                                          locked_class_name=self.locked_class_name, username=username),
            "birthdays": BirthdaysPage(self.content, locked_stage_id=self.locked_stage_id,
                                         locked_class_name=self.locked_class_name),
            "reports": ReportsPage(self.content, locked_stage_id=self.locked_stage_id),
            "lessons": LessonsPage(self.content, locked_stage_id=self.locked_stage_id, username=username),
            "verse": VersePage(self.content),
        }
        if self.is_admin:
            self.pages["stages"] = StagesPage(self.content, refresh_callback=self.refresh_all, username=username)
            self.pages["users"] = UsersPage(self.content)
            self.pages["activity_log"] = ActivityLogPage(self.content)

        for page in self.pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.sidebar.set_active("dashboard")
        self.show_page("dashboard")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # اختصارات لوحة المفاتيح: Ctrl+S للحفظ في الصفحة الحالية، Ctrl+N لمخدوم جديد
        self.bind_all("<Control-s>", self._on_ctrl_s)
        self.bind_all("<Control-n>", self._on_ctrl_n)

    def _on_ctrl_s(self, event=None):
        page = self.pages.get(self.sidebar.active_key)
        if page and hasattr(page, "ctrl_s_action"):
            page.ctrl_s_action()

    def _on_ctrl_n(self, event=None):
        if self.sidebar.active_key == "students":
            self.pages["students"].clear_form()

    def show_page(self, key):
        self.sidebar.set_active(key)
        page = self.pages[key]
        page.tkraise()
        if hasattr(page, "refresh"):
            page.refresh()

    def refresh_all(self):
        # كل صفحة بتتحدّث لوحدها أول ما تتفتح (show_page)، فيكفي نحدّث الصفحة الحالية بس
        # (كل تحديث دلوقتي معناه طلبات للسيرفر، فمنوفّرها).
        page = self.pages.get(self.sidebar.active_key)
        if page is not None and hasattr(page, "refresh"):
            page.refresh()

    def on_close(self):
        # النسخ الاحتياطي بقى على السيرفر (تلقائي يوميًا + يدوي من صفحة المستخدمين)
        try:
            db.logout()
        except Exception:
            pass
        self.destroy()

    def report_callback_exception(self, exc, val, tb):
        """أي خطأ اتصال/سيرفر جوه أي زرار بيظهر للمستخدم كرسالة واضحة بدل ما يختفي في الـ console."""
        if isinstance(val, SessionExpired):
            messagebox.showerror("انتهت الجلسة", "جلسة الدخول انتهت. أعد تشغيل البرنامج وسجّل دخول من جديد.")
            self.destroy()
        elif isinstance(val, ApiError):
            messagebox.showerror("خطأ", val.message)
        else:
            import traceback
            traceback.print_exception(exc, val, tb)
            messagebox.showerror("خطأ غير متوقع", str(val))


# =========================================================
# صفحة: الرئيسية (Dashboard)
# =========================================================
class DashboardPage(tk.Frame):
    def __init__(self, parent, locked_stage_id=None, locked_class_name=None, go_to_page=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.locked_stage_id = locked_stage_id
        self.locked_class_name = locked_class_name
        self.go_to_page = go_to_page
        self._build_ui()

    def _build_ui(self):
        page_header(self, "الرئيسية", "نظرة سريعة على الخدمة")

        self.body = tk.Frame(self, bg=COLORS["bg"])
        self.body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

    def _stat_card(self, parent, icon, value, label, color, on_click=None):
        outer, inner = card(parent)
        pad = tk.Frame(inner, bg=COLORS["card_bg"], cursor="hand2" if on_click else "")
        pad.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(pad, text=icon, font=("Segoe UI", 22), bg=COLORS["card_bg"]).pack(anchor="e")
        tk.Label(pad, text=str(value), font=("Segoe UI", 24, "bold"), bg=COLORS["card_bg"],
                  fg=color).pack(anchor="e", pady=(4, 0))
        tk.Label(pad, text=label, font=FONTS["small"], bg=COLORS["card_bg"],
                  fg=COLORS["text_muted"]).pack(anchor="e")
        if on_click:
            for widget in (pad, *pad.winfo_children()):
                widget.bind("<Button-1>", lambda e: on_click())
        return outer

    def refresh(self):
        for w in self.body.winfo_children():
            w.destroy()

        stage_id = self.locked_stage_id
        stats = db.get_dashboard_stats(stage_id=stage_id, class_name=self.locked_class_name)

        # تنبيه: مراحل معادها اليوم ولسه محدش سجّل حضور
        missing = db.get_stages_missing_attendance_today()
        if self.locked_stage_id is not None:
            missing = [s for s in missing if s["id"] == self.locked_stage_id]
        if missing:
            names = "، ".join(s["name"] for s in missing)
            banner = pill_label(self.body, f"📅 معاد اجتماع اليوم لـ: {names} — ولسه ما سُجّلش حضور",
                                  bg=COLORS["warning_light"], fg=COLORS["warning"])
            banner.pack(fill="x", pady=(0, 14), ipady=6)

        cards_row = tk.Frame(self.body, bg=COLORS["bg"])
        cards_row.pack(fill="x", pady=(0, 16))
        for i in range(4):
            cards_row.columnconfigure(i, weight=1)

        pct_text = f"{stats['attendance_pct_today']}%" if stats["attendance_pct_today"] is not None else "—"
        c1 = self._stat_card(cards_row, "👥", stats["total_students"], "إجمالي المخدومين",
                               COLORS["primary"], lambda: self.go_to_page("students"))
        c1.grid(row=0, column=3, sticky="nsew", padx=4)
        c2 = self._stat_card(cards_row, "📋", pct_text, "نسبة حضور اليوم",
                               COLORS["success"], lambda: self.go_to_page("attendance"))
        c2.grid(row=0, column=2, sticky="nsew", padx=4)
        c3 = self._stat_card(cards_row, "⚠️", stats["needs_visit_count"], "يحتاجون افتقاد",
                               COLORS["danger"], lambda: self.go_to_page("attendance"))
        c3.grid(row=0, column=1, sticky="nsew", padx=4)
        c4 = self._stat_card(cards_row, "🎂", stats["upcoming_birthdays_count"], "أعياد ميلاد قريبة",
                               COLORS["warning"], lambda: self.go_to_page("birthdays"))
        c4.grid(row=0, column=0, sticky="nsew", padx=4)

        bottom_row = tk.Frame(self.body, bg=COLORS["bg"])
        bottom_row.pack(fill="both", expand=True)
        bottom_row.columnconfigure(0, weight=1)
        bottom_row.columnconfigure(1, weight=1)

        # بطاقة: يحتاجون افتقاد
        visit_outer, visit_card = card(bottom_row)
        visit_outer.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        visit_pad = tk.Frame(visit_card, bg=COLORS["card_bg"])
        visit_pad.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(visit_pad, text="⚠️ يحتاجون افتقاد", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["danger"], anchor="e").pack(fill="x", pady=(0, 8))
        if not stats["needs_visit"]:
            tk.Label(visit_pad, text="لا يوجد حاليًا ✅", font=FONTS["small"], bg=COLORS["card_bg"],
                      fg=COLORS["text_muted"], anchor="e").pack(fill="x")
        else:
            for a in stats["needs_visit"]:
                tk.Label(visit_pad, text=f'• {a["name"]} (غاب {a["absences"]})', font=FONTS["body"],
                          bg=COLORS["card_bg"], fg=COLORS["text_main"], anchor="e").pack(fill="x", pady=2)

        # بطاقة: أقرب عيد ميلاد
        bday_outer, bday_card = card(bottom_row)
        bday_outer.grid(row=0, column=0, sticky="nsew", padx=(8, 0))
        bday_pad = tk.Frame(bday_card, bg=COLORS["card_bg"])
        bday_pad.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(bday_pad, text="🎂 أقرب عيد ميلاد", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["warning"], anchor="e").pack(fill="x", pady=(0, 8))
        if not stats["nearest_birthday"]:
            tk.Label(bday_pad, text="لا يوجد خلال 7 أيام", font=FONTS["small"], bg=COLORS["card_bg"],
                      fg=COLORS["text_muted"], anchor="e").pack(fill="x")
        else:
            student, bd_date, delta = stats["nearest_birthday"]
            when = "اليوم! 🎉" if delta == 0 else f"بعد {delta} يوم/أيام"
            tk.Label(bday_pad, text=f'{student["name"]} — {when}', font=FONTS["body_bold"],
                      bg=COLORS["card_bg"], fg=COLORS["text_main"], anchor="e").pack(fill="x")


# =========================================================
# صفحة: المخدومين
# =========================================================
class StudentsPage(tk.Frame):
    def __init__(self, parent, locked_stage_id=None, locked_class_name=None, username=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.locked_stage_id = locked_stage_id  # لو مش None، الخادم مقفول على مرحلة واحدة بس
        self.locked_class_name = locked_class_name  # لو مش None، الخادم مقفول على فصل واحد جوه المرحلة
        self.username = username
        self.selected_id = None
        self.stage_choices = []
        self.filter_stage_choices = []
        self.family_choices = []
        self.pending_photo_path = None   # مسار الصورة المختارة قبل الحفظ
        self.photo_image_ref = None      # مرجع لمنع جمع القمامة للصورة المعروضة
        self._build_ui()

    def _build_ui(self):
        page_header(self, "المخدومين", "إضافة وتعديل وحذف بيانات المخدومين")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # بطاقة النموذج
        form_outer, form_card = card(body)
        form_outer.pack(fill="x", pady=(0, 16))

        form_head = tk.Frame(form_card, bg=COLORS["card_bg"])
        form_head.pack(fill="x", padx=20, pady=(18, 6))
        ttk.Button(form_head, text="📥 استيراد من إكسل", style="Secondary.TButton",
                    command=self.import_from_excel).pack(side="left", padx=(0, 6))
        ttk.Button(form_head, text="🗑️ سلة المحذوفات", style="Secondary.TButton",
                    command=self.open_trash).pack(side="left")
        tk.Label(form_head, text="بيانات المخدوم", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(side="right", fill="x", expand=True, padx=(12, 0))

        form_body = tk.Frame(form_card, bg=COLORS["card_bg"])
        form_body.pack(fill="x", padx=20, pady=(0, 18))

        # عمود الصورة (يمين الفورم)
        photo_col = tk.Frame(form_body, bg=COLORS["card_bg"])
        photo_col.pack(side="right", padx=(16, 0))
        self.photo_label = tk.Label(photo_col, text="بدون صورة", width=12, height=6,
                                      bg="#F0F1F7", fg=COLORS["text_muted"], font=FONTS["small"])
        self.photo_label.pack()
        ttk.Button(photo_col, text="📷 اختيار صورة", style="Secondary.TButton",
                    command=self.choose_photo).pack(pady=(8, 0), fill="x")
        ttk.Button(photo_col, text="📅 سجل الحضور", style="Secondary.TButton",
                    command=self.show_attendance_history).pack(pady=(6, 0), fill="x")

        form_pad = tk.Frame(form_body, bg=COLORS["card_bg"])
        form_pad.pack(side="right", fill="x", expand=True, padx=(0, 16))

        ttk.Label(form_pad, text="الاسم", style="Body.TLabel").grid(row=0, column=3, sticky="e", padx=6, pady=6)
        self.name_var = tk.StringVar()
        name_vcmd = (self.register(self._validate_name_input), "%P")
        ttk.Entry(form_pad, textvariable=self.name_var, style="App.TEntry", width=26,
                   validate="key", validatecommand=name_vcmd).grid(row=0, column=2, padx=6)

        ttk.Label(form_pad, text="الهاتف (01xxxxxxxxx)", style="Body.TLabel").grid(row=0, column=1, sticky="e", padx=6)
        self.phone_var = tk.StringVar()
        phone_vcmd = (self.register(self._validate_phone_input), "%P")
        ttk.Entry(form_pad, textvariable=self.phone_var, style="App.TEntry", width=20,
                   validate="key", validatecommand=phone_vcmd).grid(row=0, column=0, padx=6)

        ttk.Label(form_pad, text="تاريخ الميلاد (مثال: 2000-08-30 أو 30/08/2000)", style="Body.TLabel").grid(row=1, column=3, sticky="e", padx=6, pady=6)
        self.birth_var = tk.StringVar()
        ttk.Entry(form_pad, textvariable=self.birth_var, style="App.TEntry", width=26).grid(row=1, column=2, padx=6)

        ttk.Label(form_pad, text="الفصل / المجموعة", style="Body.TLabel").grid(row=1, column=1, sticky="e", padx=6)
        self.class_var = tk.StringVar()
        class_vcmd = (self.register(self._validate_name_input), "%P")
        self.class_entry = ttk.Entry(form_pad, textvariable=self.class_var, style="App.TEntry", width=20,
                                       validate="key", validatecommand=class_vcmd)
        self.class_entry.grid(row=1, column=0, padx=6)

        ttk.Label(form_pad, text="المرحلة", style="Body.TLabel").grid(row=2, column=3, sticky="e", padx=6, pady=6)
        self.stage_var = tk.StringVar()
        self.stage_combo = ttk.Combobox(form_pad, textvariable=self.stage_var, style="App.TCombobox",
                                          width=24, state="readonly")
        self.stage_combo.grid(row=2, column=2, padx=6, sticky="w")

        ttk.Label(form_pad, text="تاريخ الانضمام (YYYY-MM-DD)", style="Body.TLabel").grid(row=2, column=1, sticky="e", padx=6)
        self.join_date_var = tk.StringVar()
        ttk.Entry(form_pad, textvariable=self.join_date_var, style="App.TEntry", width=20).grid(row=2, column=0, padx=6)

        ttk.Label(form_pad, text="التصنيف", style="Body.TLabel").grid(row=3, column=3, sticky="e", padx=6, pady=6)
        self.tag_var = tk.StringVar()
        tag_combo = ttk.Combobox(form_pad, textvariable=self.tag_var, style="App.TCombobox", width=24,
                                   state="readonly", values=["بدون تصنيف"] + db.TAGS[1:])
        tag_combo.grid(row=3, column=2, padx=6, sticky="w")

        ttk.Label(form_pad, text="العائلة", style="Body.TLabel").grid(row=3, column=1, sticky="e", padx=6)
        family_row = tk.Frame(form_pad, bg=COLORS["card_bg"])
        family_row.grid(row=3, column=0, padx=6, sticky="w")
        self.family_var = tk.StringVar()
        self.family_combo = ttk.Combobox(family_row, textvariable=self.family_var, style="App.TCombobox",
                                           width=16, state="readonly")
        self.family_combo.pack(side="right")
        ttk.Button(family_row, text="+", width=2, style="Secondary.TButton",
                    command=self.add_new_family).pack(side="right", padx=(4, 0))

        ttk.Label(form_pad, text="ملاحظات", style="Body.TLabel").grid(row=4, column=3, sticky="ne", padx=6, pady=6)
        self.notes_text = tk.Text(form_pad, width=50, height=3, font=FONTS["body"], wrap="word",
                                    relief="flat", highlightthickness=1, highlightbackground=COLORS["card_border"])
        self.notes_text.grid(row=4, column=0, columnspan=3, padx=6, pady=6, sticky="we")

        self.family_members_label = tk.Label(form_pad, text="", font=FONTS["small"], bg=COLORS["card_bg"],
                                               fg=COLORS["primary"], anchor="e", wraplength=550, justify="right")
        self.family_members_label.grid(row=5, column=0, columnspan=4, sticky="we", padx=6)

        btns = tk.Frame(form_pad, bg=COLORS["card_bg"])
        btns.grid(row=6, column=0, columnspan=4, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="➕ إضافة مخدوم", style="Primary.TButton", command=self.add_student).pack(side="right", padx=4)
        ttk.Button(btns, text="حفظ التعديل", style="Secondary.TButton", command=self.update_student).pack(side="right", padx=4)
        ttk.Button(btns, text="حذف", style="Danger.TButton", command=self.delete_student).pack(side="right", padx=4)
        ttk.Button(btns, text="مسح الحقول", style="Secondary.TButton", command=self.clear_form).pack(side="right", padx=4)

        # بطاقة الجدول
        table_outer, table_card = card(body)
        table_outer.pack(fill="both", expand=True)
        table_pad = tk.Frame(table_card, bg=COLORS["card_bg"])
        table_pad.pack(fill="both", expand=True, padx=16, pady=16)

        filter_row = tk.Frame(table_pad, bg=COLORS["card_bg"])
        filter_row.pack(fill="x", pady=(0, 10))
        self.filter_var = tk.StringVar()
        self.filter_combo = ttk.Combobox(filter_row, textvariable=self.filter_var, style="App.TCombobox",
                                           width=18, state="readonly")
        self.filter_combo.pack(side="right")
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(filter_row, text="المرحلة:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_row, textvariable=self.search_var, style="App.TEntry", width=22)
        search_entry.pack(side="right", padx=(0, 14))
        search_entry.bind("<KeyRelease>", lambda e: self._schedule_search())
        ttk.Label(filter_row, text="🔍 بحث بالاسم:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        columns = ("id", "name", "age", "phone", "birthdate", "class_name", "stage_name", "tag")
        self.tree = ttk.Treeview(table_pad, columns=columns, show="headings", height=10, style="App.Treeview")
        headings = {"id": "#", "name": "الاسم", "age": "العمر", "phone": "الهاتف", "birthdate": "تاريخ الميلاد",
                    "class_name": "الفصل", "stage_name": "المرحلة", "tag": "التصنيف"}
        widths = {"id": 40, "name": 140, "age": 55, "phone": 110, "birthdate": 100, "class_name": 90,
                  "stage_name": 100, "tag": 130}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, anchor="center", width=widths[col])
        self.tree.tag_configure("odd", background="#FAFBFF")
        self.tree.tag_configure("even", background="#FFFFFF")
        for tag_name, (bg, fg) in TAG_COLORS.items():
            self.tree.tag_configure(f"badge_{tag_name}", background=bg, foreground=fg)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def _reload_stage_choices(self):
        if self.locked_stage_id is not None:
            # خادم مقفول على مرحلة واحدة: الفلتر والفورم يعرضوا هذه المرحلة فقط، معطّلين
            stages = db.get_all_stages()
            name = next((s["name"] for s in stages if s["id"] == self.locked_stage_id), "مرحلتي")
            self.filter_stage_choices = [(name, self.locked_stage_id)]
            self.filter_combo["values"] = [name]
            self.filter_var.set(name)
            self.filter_combo.configure(state="disabled")

            self.stage_choices = [(name, self.locked_stage_id)]
            self.stage_combo["values"] = [name]
            self.stage_var.set(name)
            self.stage_combo.configure(state="disabled")

            # لو الخادم مقفول كمان على فصل واحد بعينه جوه المرحلة، نجبر حقل الفصل عليه ونعطّله
            if self.locked_class_name:
                self.class_var.set(self.locked_class_name)
                self.class_entry.configure(state="disabled")
            return

        self.filter_stage_choices = get_stage_choices(include_all=True, include_unset=True)
        current_filter = self.filter_var.get()
        self.filter_combo["values"] = [c[0] for c in self.filter_stage_choices]
        if current_filter not in self.filter_combo["values"]:
            self.filter_var.set(self.filter_stage_choices[0][0])

        self.stage_choices = get_stage_choices(include_all=False, include_unset=True)
        self.stage_combo["values"] = [c[0] for c in self.stage_choices]
        if not self.stage_var.get() and self.stage_choices:
            self.stage_var.set(self.stage_choices[-1][0])

    def _reload_family_choices(self):
        families = db.get_all_families()
        self.family_choices = [("بدون عائلة", None)] + [(f["name"], f["id"]) for f in families]
        self.family_combo["values"] = [c[0] for c in self.family_choices]
        if not self.family_var.get():
            self.family_var.set("بدون عائلة")

    def _selected_filter_stage_id(self):
        if self.locked_stage_id is not None:
            return self.locked_stage_id
        label = self.filter_var.get()
        for lbl, sid in self.filter_stage_choices:
            if lbl == label:
                return sid
        return None

    def _selected_form_stage_id(self):
        if self.locked_stage_id is not None:
            return self.locked_stage_id
        label = self.stage_var.get()
        for lbl, sid in self.stage_choices:
            if lbl == label:
                return sid
        return None

    def _selected_family_id(self):
        label = self.family_var.get()
        for lbl, fid in self.family_choices:
            if lbl == label:
                return fid
        return None

    def _schedule_search(self):
        """بحث مؤجّل: ننتظر 350 ميلي ثانية بعد آخر ضغطة قبل ما نكلّم السيرفر (مش طلب لكل حرف)."""
        if getattr(self, "_search_job", None):
            self.after_cancel(self._search_job)
        self._search_job = self.after(350, self._fill_table)

    def refresh(self):
        self._reload_stage_choices()
        self._reload_family_choices()
        self._fill_table()

    def _fill_table(self):
        self._search_job = None
        for row in self.tree.get_children():
            self.tree.delete(row)
        stage_filter = self._selected_filter_stage_id()
        search = self.search_var.get().strip()
        for i, s in enumerate(db.get_all_students(stage_id=stage_filter, search=search,
                                                    class_name=self.locked_class_name)):
            base_tag = "odd" if i % 2 else "even"
            age = db.calculate_age(s["birthdate"])
            tag_display = s["tag"] or ""
            row_tags = (base_tag,)
            item_id = self.tree.insert("", "end", values=(
                s["id"], s["name"], age if age is not None else "", s["phone"] or "",
                s["birthdate"] or "", s["class_name"] or "", s["stage_name"] or "بدون مرحلة", tag_display
            ), tags=row_tags)
            if tag_display in TAG_COLORS:
                bg, fg = TAG_COLORS[tag_display]
                self.tree.tag_configure(f"row_{item_id}", background=bg)

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        self.selected_id = int(values[0])
        self.name_var.set(values[1])
        self.phone_var.set(values[3])
        self.birth_var.set(values[4])
        self.class_var.set(values[5])
        if self.locked_stage_id is None:
            stage_label = values[6]
            if stage_label in self.stage_combo["values"]:
                self.stage_var.set(stage_label)
            else:
                self.stage_var.set("بدون مرحلة")

        # جلب التفاصيل الإضافية (ملاحظات/تاريخ انضمام/صورة/عائلة/تصنيف) من قاعدة البيانات مباشرة
        full = db.get_student(self.selected_id)
        self.notes_text.delete("1.0", "end")
        if full:
            self.notes_text.insert("1.0", full["notes"] or "")
            self.join_date_var.set(full["join_date"] or "")
            self._show_photo(db.fetch_student_photo(self.selected_id) if full["photo_path"] else None)
            self.tag_var.set(full["tag"] or "بدون تصنيف")
            family_label = full["family_name"] or "بدون عائلة"
            if family_label in self.family_combo["values"]:
                self.family_var.set(family_label)
            self._update_family_members_label(full["family_id"])
        self.pending_photo_path = None

    def _update_family_members_label(self, family_id):
        if not family_id:
            self.family_members_label.config(text="")
            return
        members = db.get_family_members(family_id, exclude_student_id=self.selected_id)
        if members:
            names = "، ".join(m["name"] for m in members)
            self.family_members_label.config(text=f"👪 أفراد نفس العائلة: {names}")
        else:
            self.family_members_label.config(text="")

    def add_new_family(self):
        name = simpledialog.askstring("عائلة جديدة", "اسم العائلة:")
        if name and name.strip():
            db.get_or_create_family(name.strip())
            self._reload_family_choices()
            self.family_var.set(name.strip())

    def _show_photo(self, photo_path):
        if photo_path and os.path.exists(photo_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(photo_path)
                img.thumbnail((100, 100))
                self.photo_image_ref = ImageTk.PhotoImage(img)
                self.photo_label.configure(image=self.photo_image_ref, text="", width=100, height=100)
                return
            except Exception:
                pass
        self.photo_image_ref = None
        self.photo_label.configure(image="", text="بدون صورة", width=12, height=6)

    def choose_photo(self):
        filepath = filedialog.askopenfilename(
            title="اختر صورة",
            filetypes=[("صور", "*.png *.jpg *.jpeg *.gif *.bmp"), ("كل الملفات", "*.*")],
        )
        if not filepath:
            return
        self.pending_photo_path = filepath
        self._show_photo(filepath)

    def show_attendance_history(self):
        if not self.selected_id:
            messagebox.showinfo("تنبيه", "اختر مخدوم من القائمة أولاً")
            return
        history = db.get_student_attendance_history(self.selected_id)
        win = tk.Toplevel(self)
        win.title(f"سجل الحضور - {self.name_var.get()}")
        win.geometry("380x480")
        win.configure(bg=COLORS["bg"])
        tk.Label(win, text=f"📅 سجل حضور: {self.name_var.get()}", font=FONTS["h2"],
                  bg=COLORS["bg"], fg=COLORS["text_main"]).pack(pady=14)
        if not history:
            tk.Label(win, text="لا يوجد سجل حضور بعد.", font=FONTS["body"],
                      bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(pady=20)
            return
        list_frame = tk.Frame(win, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for i, rec in enumerate(history):
            row_bg = "#FAFBFF" if i % 2 else "#FFFFFF"
            present = rec["present"]
            row = tk.Frame(list_frame, bg=row_bg)
            row.pack(fill="x", pady=1)
            status = "✓ حاضر" if present else "✗ غائب"
            color = COLORS["success"] if present else COLORS["danger"]
            tk.Label(row, text=status, font=FONTS["small_bold"], bg=row_bg, fg=color, width=10).pack(side="left", padx=8, pady=6)
            tk.Label(row, text=rec["session_date"], font=FONTS["body"], bg=row_bg, fg=COLORS["text_main"],
                      anchor="e").pack(side="right", padx=8, pady=6, fill="x", expand=True)

    def open_trash(self):
        deleted = db.get_deleted_students()
        win = tk.Toplevel(self)
        win.title("سلة المحذوفات")
        win.geometry("500x500")
        win.configure(bg=COLORS["bg"])
        tk.Label(win, text="🗑️ سلة المحذوفات", font=FONTS["h2"],
                  bg=COLORS["bg"], fg=COLORS["text_main"]).pack(pady=14)

        list_frame = tk.Frame(win, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        if not deleted:
            tk.Label(list_frame, text="سلة المحذوفات فاضية.", font=FONTS["body"],
                      bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(pady=20)
            return

        def do_restore(sid):
            db.restore_student(sid)
            if self.username:
                db.log_activity(self.username, "استرجاع مخدوم", f"id={sid}")
            win.destroy()
            self.refresh()

        def do_permanent_delete(sid, name):
            if messagebox.askyesno("تأكيد نهائي", f'هل تريد حذف "{name}" نهائيًا؟ لا يمكن التراجع عن هذا!'):
                db.permanently_delete_student(sid)
                if self.username:
                    db.log_activity(self.username, "حذف نهائي لمخدوم", name)
                win.destroy()
                self.open_trash()

        for i, s in enumerate(deleted):
            row_bg = "#FAFBFF" if i % 2 else "#FFFFFF"
            row = tk.Frame(list_frame, bg=row_bg)
            row.pack(fill="x", pady=1)
            ttk.Button(row, text="حذف نهائي", style="Danger.TButton",
                        command=lambda sid=s["id"], name=s["name"]: do_permanent_delete(sid, name)
                        ).pack(side="left", padx=6, pady=6)
            ttk.Button(row, text="↩️ استرجاع", style="Primary.TButton",
                        command=lambda sid=s["id"]: do_restore(sid)).pack(side="left", padx=6, pady=6)
            tk.Label(row, text=s["name"], font=FONTS["body_bold"], bg=row_bg, fg=COLORS["text_main"],
                      anchor="e").pack(side="right", padx=10, fill="x", expand=True)

    def clear_form(self):
        self.selected_id = None
        self.name_var.set("")
        self.phone_var.set("")
        self.birth_var.set("")
        self.class_var.set(self.locked_class_name or "")
        self.join_date_var.set(date.today().isoformat())
        self.notes_text.delete("1.0", "end")
        self.pending_photo_path = None
        self._show_photo(None)
        self.tag_var.set("بدون تصنيف")
        self.family_var.set("بدون عائلة")
        self.family_members_label.config(text="")
        if self.locked_stage_id is None and self.stage_choices:
            self.stage_var.set(self.stage_choices[-1][0])

    def _validate_name_input(self, proposed_text):
        """يمنع كتابة أي رقم (عربي أو إنجليزي) في حقل الاسم أثناء الكتابة."""
        return not any(ch.isdigit() for ch in proposed_text)

    def _validate_phone_input(self, proposed_text):
        """يسمح فقط بأرقام (وحتى 11 رقم) أثناء الكتابة في حقل الهاتف."""
        if proposed_text == "":
            return True
        return proposed_text.isdigit() and len(proposed_text) <= 11

    def _validate_birthdate(self):
        """
        يتحقق من صيغة تاريخ الميلاد المدخل ويوحّدها لـ YYYY-MM-DD.
        يرجع (نص التاريخ الموحّد, صحيح) - لو النص فاضي يرجع ("", True) لأنه اختياري.
        لو الصيغة غير مفهومة يعرض تنبيه فورًا بدل ما يختفي المخدوم من صفحة الأعياد بصمت لاحقًا.
        """
        text = self.birth_var.get().strip()
        if not text:
            return "", True
        parsed = db.parse_flexible_date(text)
        if parsed is None:
            messagebox.showwarning(
                "تنبيه",
                "تاريخ الميلاد غير مفهوم. استخدم صيغة مثل 2000-08-30 أو 30/08/2000 أو 30-08-2000."
            )
            return "", False
        normalized = parsed.isoformat()
        self.birth_var.set(normalized)  # نوحّد الشكل المعروض في الحقل نفسه
        return normalized, True

    def _tag_value(self):
        t = self.tag_var.get()
        return "" if t == "بدون تصنيف" else t

    def ctrl_s_action(self):
        """يُستدعى عند الضغط على Ctrl+S: يحفظ تعديل لو فيه مخدوم مختار، وإلا يضيف مخدوم جديد."""
        if self.selected_id:
            self.update_student()
        else:
            self.add_student()

    def add_student(self):
        if not self.name_var.get().strip():
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم المخدوم")
            return
        if any(ch.isdigit() for ch in self.name_var.get()):
            messagebox.showwarning("تنبيه", "اسم المخدوم يجب ألا يحتوي على أرقام")
            return
        if any(ch.isdigit() for ch in self.class_var.get()):
            messagebox.showwarning("تنبيه", "الفصل / المجموعة يجب ألا يحتوي على أرقام")
            return
        if not db.is_valid_egyptian_phone(self.phone_var.get()):
            messagebox.showwarning("تنبيه", "رقم الهاتف غير صحيح. يجب أن يكون 11 رقمًا ويبدأ بـ 010 أو 011 أو 012 أو 015")
            return
        birthdate, ok = self._validate_birthdate()
        if not ok:
            return
        new_id = db.add_student(self.name_var.get().strip(), self.phone_var.get().strip(),
                                birthdate, self.class_var.get().strip(),
                                self._selected_form_stage_id(),
                                notes=self.notes_text.get("1.0", "end").strip(),
                                join_date=self.join_date_var.get().strip(),
                                family_id=self._selected_family_id(),
                                tag=self._tag_value())
        if self.pending_photo_path:
            db.save_student_photo_file(new_id, self.pending_photo_path)
        self.clear_form()
        self.refresh()

    def update_student(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "الرجاء اختيار مخدوم من القائمة أولاً")
            return
        if any(ch.isdigit() for ch in self.name_var.get()):
            messagebox.showwarning("تنبيه", "اسم المخدوم يجب ألا يحتوي على أرقام")
            return
        if any(ch.isdigit() for ch in self.class_var.get()):
            messagebox.showwarning("تنبيه", "الفصل / المجموعة يجب ألا يحتوي على أرقام")
            return
        if not db.is_valid_egyptian_phone(self.phone_var.get()):
            messagebox.showwarning("تنبيه", "رقم الهاتف غير صحيح. يجب أن يكون 11 رقمًا ويبدأ بـ 010 أو 011 أو 012 أو 015")
            return
        birthdate, ok = self._validate_birthdate()
        if not ok:
            return
        db.update_student(self.selected_id, self.name_var.get().strip(), self.phone_var.get().strip(),
                           birthdate, self.class_var.get().strip(),
                           self._selected_form_stage_id(),
                           notes=self.notes_text.get("1.0", "end").strip(),
                           join_date=self.join_date_var.get().strip(),
                           family_id=self._selected_family_id(),
                           tag=self._tag_value())
        if self.pending_photo_path:
            db.save_student_photo_file(self.selected_id, self.pending_photo_path)
        if self.username:
            db.log_activity(self.username, "تعديل مخدوم", self.name_var.get().strip())
        self.clear_form()
        self.refresh()

    def delete_student(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "الرجاء اختيار مخدوم من القائمة أولاً")
            return
        name = self.name_var.get().strip()
        if messagebox.askyesno("تأكيد", f'هل تريد نقل "{name}" لسلة المحذوفات؟ (يمكن استرجاعه لاحقًا)'):
            db.delete_student(self.selected_id)
            if self.username:
                db.log_activity(self.username, "حذف مخدوم (نقل لسلة المحذوفات)", name)
            self.clear_form()
            self.refresh()

    def import_from_excel(self):
        filepath = filedialog.askopenfilename(
            title="اختر ملف إكسل",
            filetypes=[("ملفات إكسل", "*.xlsx"), ("كل الملفات", "*.*")],
        )
        if not filepath:
            return
        result = db.import_students_from_excel(filepath)
        msg = f"تم استيراد {result['imported']} مخدوم بنجاح."
        if result["skipped"]:
            msg += f"\nتم تجاهل {result['skipped']} صف (بدون اسم أو به خطأ)."
        if result["errors"]:
            msg += "\n\nتفاصيل:\n" + "\n".join(result["errors"][:8])
        messagebox.showinfo("نتيجة الاستيراد", msg)
        if self.username:
            db.log_activity(self.username, "استيراد من إكسل", f"{result['imported']} مخدوم")
        self.refresh()


# =========================================================
# صفحة: المراحل
# =========================================================
class StagesPage(tk.Frame):
    def __init__(self, parent, refresh_callback=None, username=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.refresh_callback = refresh_callback
        self.username = username
        self._build_ui()

    def _build_ui(self):
        page_header(self, "المراحل", "قسّم المخدومين إلى مراحل (مثال: ابتدائي، إعدادي، ثانوي) حتى لا تتداخل بياناتهم")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # بطاقة إضافة مرحلة
        form_outer, form_card = card(body)
        form_outer.pack(fill="x", pady=(0, 16))
        tk.Label(form_card, text="إضافة مرحلة جديدة", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(fill="x", padx=20, pady=(18, 6))

        form_row = tk.Frame(form_card, bg=COLORS["card_bg"])
        form_row.pack(fill="x", padx=20, pady=(0, 18))
        ttk.Button(form_row, text="➕ إضافة", style="Primary.TButton",
                    command=self.add_stage).pack(side="left")
        self.meeting_day_var = tk.StringVar()
        day_combo = ttk.Combobox(form_row, textvariable=self.meeting_day_var, style="App.TCombobox",
                                   width=12, state="readonly",
                                   values=["", "السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"])
        day_combo.pack(side="right", padx=(0, 10))
        ttk.Label(form_row, text="يوم الاجتماع", style="Body.TLabel").pack(side="right", padx=6)
        self.new_stage_var = tk.StringVar()
        entry = ttk.Entry(form_row, textvariable=self.new_stage_var, style="App.TEntry", width=24)
        entry.pack(side="right", padx=(0, 10))
        entry.bind("<Return>", lambda e: self.add_stage())
        ttk.Label(form_row, text="اسم المرحلة", style="Body.TLabel").pack(side="right", padx=6)

        # بطاقة قائمة المراحل
        list_outer, list_card = card(body)
        list_outer.pack(fill="both", expand=True)
        list_pad = tk.Frame(list_card, bg=COLORS["card_bg"])
        list_pad.pack(fill="both", expand=True, padx=20, pady=20)

        self.list_container = tk.Frame(list_pad, bg=COLORS["card_bg"])
        self.list_container.pack(fill="both", expand=True)

    def refresh(self):
        for widget in self.list_container.winfo_children():
            widget.destroy()

        stages = db.get_all_stages()
        if not stages:
            tk.Label(self.list_container, text="لا توجد مراحل مضافة بعد. أضف أول مرحلة أعلاه.",
                      font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(pady=10)
            return

        for i, s in enumerate(stages):
            count = s["student_count"] if "student_count" in s else db.count_students_in_stage(s["id"])
            row_bg = "#FAFBFF" if i % 2 else COLORS["card_bg"]
            row = tk.Frame(self.list_container, bg=row_bg)
            row.pack(fill="x", pady=2)

            ttk.Button(row, text="حذف", style="Danger.TButton",
                        command=lambda sid=s["id"], name=s["name"]: self.delete_stage(sid, name)
                        ).pack(side="left", padx=10, pady=8)

            tk.Label(row, text=f'{count} مخدوم', font=FONTS["small"], bg=row_bg,
                      fg=COLORS["text_muted"]).pack(side="right", padx=(0, 14), pady=8)
            if s["meeting_day"]:
                tk.Label(row, text=f'📅 {s["meeting_day"]}', font=FONTS["small"], bg=row_bg,
                          fg=COLORS["primary"]).pack(side="right", padx=(0, 14), pady=8)
            tk.Label(row, text=f'🏷️ {s["name"]}', font=FONTS["body_bold"], bg=row_bg,
                      fg=COLORS["text_main"], anchor="e").pack(side="right", padx=10, pady=8)

    def add_stage(self):
        name = self.new_stage_var.get().strip()
        if not name:
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم المرحلة")
            return
        db.add_stage(name, self.meeting_day_var.get().strip() or None)
        if self.username:
            db.log_activity(self.username, "إضافة مرحلة", name)
        self.new_stage_var.set("")
        self.meeting_day_var.set("")
        self.refresh()
        if self.refresh_callback:
            self.refresh_callback()

    def delete_stage(self, stage_id, name):
        count = db.count_students_in_stage(stage_id)
        msg = f"هل تريد حذف مرحلة \"{name}\"؟"
        if count:
            msg += f"\n\nيوجد {count} مخدوم في هذه المرحلة، سيصبحون بدون مرحلة (لن يتم حذفهم)."
        if messagebox.askyesno("تأكيد الحذف", msg):
            db.delete_stage(stage_id)
            if self.username:
                db.log_activity(self.username, "حذف مرحلة", name)
            self.refresh()
            if self.refresh_callback:
                self.refresh_callback()


# =========================================================
# صفحة: الحضور والغياب
# =========================================================
class AttendancePage(tk.Frame):
    def __init__(self, parent, refresh_callback=None, locked_stage_id=None, locked_class_name=None, username=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.refresh_callback = refresh_callback
        self.locked_stage_id = locked_stage_id
        self.locked_class_name = locked_class_name
        self.username = username
        self.check_vars = {}
        self.stage_choices = []
        self.class_choices = []
        self._build_ui()

    def ctrl_s_action(self):
        self.save_attendance()

    def _build_ui(self):
        page_header(self, "الحضور والغياب", f"تسجيل حضور اليوم: {date.today().isoformat()}")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # بطاقة قائمة الحضور
        list_outer, list_card = card(body)
        list_outer.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        list_pad = tk.Frame(list_card, bg=COLORS["card_bg"])
        list_pad.pack(fill="both", expand=True, padx=16, pady=16)

        head_row = tk.Frame(list_pad, bg=COLORS["card_bg"])
        head_row.pack(fill="x", pady=(0, 6))
        ttk.Button(head_row, text="💾 حفظ الحضور", style="Primary.TButton",
                    command=self.save_attendance).pack(side="left")
        tk.Label(head_row, text="دوس على أي مخدوم عشان تبدّل حاضر / غائب", font=FONTS["h2"],
                  bg=COLORS["card_bg"], fg=COLORS["text_main"], anchor="e").pack(side="right", fill="x", expand=True, padx=(12, 0))

        filter_row = tk.Frame(list_pad, bg=COLORS["card_bg"])
        filter_row.pack(fill="x", pady=(0, 4))
        self.stage_var = tk.StringVar()
        self.stage_combo = ttk.Combobox(filter_row, textvariable=self.stage_var, style="App.TCombobox",
                                          width=20, state="readonly")
        self.stage_combo.pack(side="right")
        self.stage_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(filter_row, text="المرحلة:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        self.class_var = tk.StringVar()
        self.class_combo = ttk.Combobox(filter_row, textvariable=self.class_var, style="App.TCombobox",
                                          width=18, state="readonly")
        self.class_combo.pack(side="right", padx=(16, 0))
        self.class_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(filter_row, text="الفصل:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        self.meeting_day_label = tk.Label(list_pad, text="", font=FONTS["small"],
                                            bg=COLORS["card_bg"], fg=COLORS["primary"], anchor="e")
        self.meeting_day_label.pack(fill="x", pady=(0, 6))

        # جدول الحضور: مجموعة لكل فصل، وصف لكل مخدوم داخله
        table_wrap = tk.Frame(list_pad, bg=COLORS["card_bg"])
        table_wrap.pack(fill="both", expand=True)

        columns = ("status",)
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="tree headings",
                                   height=14, style="App.Treeview")
        self.tree.heading("#0", text="الاسم / الفصل", anchor="e")
        self.tree.heading("status", text="الحالة")
        self.tree.column("#0", anchor="e", width=260, stretch=True)
        self.tree.column("status", anchor="center", width=110, stretch=False)

        tree_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview,
                                      style="App.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="right", fill="both", expand=True)
        tree_scroll.pack(side="left", fill="y")

        self.tree.tag_configure("class_header", background=COLORS["primary_light"],
                                  foreground=COLORS["primary"], font=FONTS["small_bold"])
        self.tree.tag_configure("present", background="#E9F9EF")
        self.tree.tag_configure("absent", background="#FAFBFF")
        self.tree.bind("<Button-1>", self._on_tree_click)

        self.item_to_student = {}  # item_id -> student_id (صفوف المخدومين فقط، مش صفوف عناوين الفصول)

        # بطاقة تنبيه الافتقاد
        alert_outer, alert_card = card(body)
        alert_outer.grid(row=0, column=0, sticky="nsew", padx=(10, 0))
        alert_pad = tk.Frame(alert_card, bg=COLORS["card_bg"])
        alert_pad.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(alert_pad, text="⚠️ يحتاجون افتقاد", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["danger"]).pack(anchor="e")
        tk.Label(alert_pad, text="غابوا مرتين أو أكثر من آخر 3 جلسات لنفس المرحلة", font=FONTS["small"],
                  bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="e", pady=(0, 10))

        self.alert_container = tk.Frame(alert_pad, bg=COLORS["card_bg"])
        self.alert_container.pack(fill="both", expand=True)

    def _selected_stage_id(self):
        if self.locked_stage_id is not None:
            return self.locked_stage_id
        label = self.stage_var.get()
        for lbl, sid in self.stage_choices:
            if lbl == label:
                return sid
        return None

    def _selected_class_name(self):
        if self.locked_class_name is not None:
            return self.locked_class_name
        label = self.class_var.get()
        for lbl, val in self.class_choices:
            if lbl == label:
                return val
        return None

    def refresh(self):
        if self.locked_stage_id is not None:
            stages = db.get_all_stages()
            match = next((s for s in stages if s["id"] == self.locked_stage_id), None)
            name = match["name"] if match else "مرحلتي"
            self.stage_choices = [(name, self.locked_stage_id)]
            self.stage_combo["values"] = [name]
            self.stage_var.set(name)
            self.stage_combo.configure(state="disabled")
            meeting_day = match["meeting_day"] if match else None
        else:
            self.stage_choices = get_stage_choices(include_all=True, include_unset=True)
            current = self.stage_var.get()
            self.stage_combo["values"] = [c[0] for c in self.stage_choices]
            if current not in self.stage_combo["values"]:
                self.stage_var.set(self.stage_choices[0][0])
            meeting_day = None
            sid_for_day = self._selected_stage_id()
            if sid_for_day and sid_for_day not in (None, "unset"):
                match = next((s for s in db.get_all_stages() if s["id"] == sid_for_day), None)
                meeting_day = match["meeting_day"] if match else None

        self.meeting_day_label.config(text=f"📅 معاد اجتماع هذه المرحلة: {meeting_day}" if meeting_day else "")

        stage_id = self._selected_stage_id()

        # قائمة الفصول تعتمد على المرحلة المختارة حاليًا (كل مرحلة لها فصولها الخاصة)
        if self.locked_class_name is not None:
            self.class_choices = [(self.locked_class_name, self.locked_class_name)]
            self.class_combo["values"] = [self.locked_class_name]
            self.class_var.set(self.locked_class_name)
            self.class_combo.configure(state="disabled")
        else:
            available_classes = db.get_distinct_classes(stage_id=stage_id)
            self.class_choices = [("كل الفصول", None)] + [(c, c) for c in available_classes] + [("بدون فصل", "unset")]
            current_class_label = self.class_var.get()
            self.class_combo["values"] = [c[0] for c in self.class_choices]
            if current_class_label not in self.class_combo["values"]:
                self.class_var.set("كل الفصول")
            self.class_combo.configure(state="readonly")

        class_name = self._selected_class_name()

        self.tree.delete(*self.tree.get_children())
        self.item_to_student = {}
        self.check_vars = {}

        today_str = date.today().isoformat()
        existing = db.get_attendance_for_date(today_str)
        students = db.get_all_students(stage_id=stage_id, class_name=class_name)

        if not students:
            self.tree.insert("", "end", text="لا يوجد مخدومون بهذا الفلتر بعد.", values=("",))
        else:
            # تجميع المخدومين حسب الفصل، وكل فصل يظهر كمجموعة منفصلة قابلة للطي
            groups = {}
            for s in students:
                class_key = s["class_name"] or "بدون فصل"
                groups.setdefault(class_key, []).append(s)

            for grp_class_name in sorted(groups.keys()):
                members = groups[grp_class_name]
                present_count = sum(1 for m in members if existing.get(m["id"], 0))
                header_text = f"📚 {grp_class_name}  ({present_count}/{len(members)} حاضر)"
                parent_id = self.tree.insert("", "end", text=header_text, values=("",),
                                               open=True, tags=("class_header",))

                for s in members:
                    present = bool(existing.get(s["id"], 0))
                    self.check_vars[s["id"]] = present
                    status_text = "✅ حاضر" if present else "❌ غائب"
                    row_tag = "present" if present else "absent"
                    child_id = self.tree.insert(parent_id, "end", text=s["name"],
                                                  values=(status_text,), tags=(row_tag,))
                    self.item_to_student[child_id] = s["id"]

        # تحديث قائمة التنبيه: كل فصل داخل كل مرحلة بمعزل تام عن الفصول الأخرى
        # (حتى لا تتداخل جلسات فصل مع فصل آخر، تمامًا كما لا تتداخل مرحلة مع أخرى)
        for widget in self.alert_container.winfo_children():
            widget.destroy()

        grouped_absentees = db.get_recent_absentees_grouped(threshold=2, lookback_sessions=3,
                                                              stage_id=stage_id, class_name=class_name)
        if not grouped_absentees:
            ok = pill_label(self.alert_container, "✅ لا يوجد حاليًا من يحتاج افتقاد عاجل",
                             bg=COLORS["success_light"], fg=COLORS["success"])
            ok.pack(anchor="e", pady=6)
        else:
            for group in grouped_absentees:
                group_label = f'{group["stage_name"]} — {group["class_name"]}' if stage_id is None else group["class_name"]
                tk.Label(self.alert_container, text=f'📚 {group_label}', font=FONTS["small_bold"],
                          bg=COLORS["card_bg"], fg=COLORS["primary"], anchor="e").pack(fill="x", pady=(8, 2))

                for a in group["absentees"]:
                    row = tk.Frame(self.alert_container, bg=COLORS["danger_light"])
                    row.pack(fill="x", pady=2)
                    top_row = tk.Frame(row, bg=COLORS["danger_light"])
                    top_row.pack(fill="x", padx=10, pady=(8, 0))
                    tk.Label(top_row, text=a["name"], font=FONTS["body_bold"],
                              bg=COLORS["danger_light"], fg=COLORS["danger"], anchor="e"
                              ).pack(side="right", fill="x", expand=True)
                    if a["phone"]:
                        msg = f'سلام {a["name"]}، افتقدناك في اجتماعاتنا الأخيرة، اطمنّا عليك 🙏'
                        ttk.Button(top_row, text="💬", width=3, style="Secondary.TButton",
                                    command=lambda p=a["phone"], m=msg: open_whatsapp(p, m)).pack(side="left")
                    tk.Label(row, text=f'غاب {a["absences"]} من آخر الجلسات', font=FONTS["small"],
                              bg=COLORS["danger_light"], fg=COLORS["text_muted"], anchor="e"
                              ).pack(fill="x", padx=10, pady=(0, 2))
                    if a["phone"]:
                        tk.Label(row, text=a["phone"], font=FONTS["small"],
                                  bg=COLORS["danger_light"], fg=COLORS["text_muted"], anchor="e"
                                  ).pack(fill="x", padx=10, pady=(0, 8))
                    else:
                        tk.Frame(row, bg=COLORS["danger_light"], height=6).pack(fill="x")

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell" and region != "tree":
            return
        row_id = self.tree.identify_row(event.y)
        if row_id not in self.item_to_student:
            return  # صف عنوان فصل، مش مخدوم - نتجاهل الضغط عليه

        student_id = self.item_to_student[row_id]
        new_present = not self.check_vars.get(student_id, False)
        self.check_vars[student_id] = new_present

        status_text = "✅ حاضر" if new_present else "❌ غائب"
        self.tree.set(row_id, "status", status_text)
        self.tree.item(row_id, tags=("present" if new_present else "absent",))

        # تحديث عدّاد الحاضرين في عنوان الفصل (الأب) مباشرة بدون إعادة تحميل كل الجدول
        parent_id = self.tree.parent(row_id)
        if parent_id:
            children = self.tree.get_children(parent_id)
            total = len(children)
            present_count = sum(
                1 for c in children if self.check_vars.get(self.item_to_student.get(c), False)
            )
            old_text = self.tree.item(parent_id, "text")
            class_label = old_text.split("(")[0].strip()
            self.tree.item(parent_id, text=f"{class_label}  ({present_count}/{total} حاضر)")

    def save_attendance(self):
        today_str = date.today().isoformat()
        db.save_attendance_bulk(today_str, self.check_vars)
        messagebox.showinfo("تم", "تم حفظ حضور اليوم بنجاح")
        self.refresh()
        if self.refresh_callback:
            self.refresh_callback()


# =========================================================
# صفحة: أعياد الميلاد
# =========================================================
class BirthdaysPage(tk.Frame):
    def __init__(self, parent, locked_stage_id=None, locked_class_name=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.locked_stage_id = locked_stage_id
        self.locked_class_name = locked_class_name
        self.stage_choices = []
        self._build_ui()

    def _build_ui(self):
        page_header(self, "أعياد الميلاد", "المخدومون الذين لهم عيد ميلاد خلال الأسبوع القادم")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        outer, inner = card(body)
        outer.pack(fill="both", expand=True)
        content = tk.Frame(inner, bg=COLORS["card_bg"])
        content.pack(fill="both", expand=True, padx=20, pady=20)

        filter_row = tk.Frame(content, bg=COLORS["card_bg"])
        filter_row.pack(fill="x", pady=(0, 12))
        self.stage_var = tk.StringVar()
        self.stage_combo = ttk.Combobox(filter_row, textvariable=self.stage_var, style="App.TCombobox",
                                          width=22, state="readonly")
        self.stage_combo.pack(side="right")
        self.stage_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(filter_row, text="المرحلة:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        self.list_frame = tk.Frame(content, bg=COLORS["card_bg"])
        self.list_frame.pack(fill="both", expand=True)

    def _selected_stage_id(self):
        if self.locked_stage_id is not None:
            return self.locked_stage_id
        label = self.stage_var.get()
        for lbl, sid in self.stage_choices:
            if lbl == label:
                return sid
        return None

    def refresh(self):
        if self.locked_stage_id is not None:
            stages = db.get_all_stages()
            name = next((s["name"] for s in stages if s["id"] == self.locked_stage_id), "مرحلتي")
            self.stage_choices = [(name, self.locked_stage_id)]
            self.stage_combo["values"] = [name]
            self.stage_var.set(name)
            self.stage_combo.configure(state="disabled")
        else:
            self.stage_choices = get_stage_choices(include_all=True, include_unset=True)
            current = self.stage_var.get()
            self.stage_combo["values"] = [c[0] for c in self.stage_choices]
            if current not in self.stage_combo["values"]:
                self.stage_var.set(self.stage_choices[0][0])
        stage_id = self._selected_stage_id()

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        upcoming = db.get_upcoming_birthdays(days_ahead=7, stage_id=stage_id, class_name=self.locked_class_name)
        if not upcoming:
            tk.Label(self.list_frame, text="لا توجد أعياد ميلاد خلال الأسبوع القادم.",
                      font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(pady=10)
            return

        for student, bd_date, delta in upcoming:
            is_today = delta == 0
            row_bg = COLORS["warning_light"] if is_today else "#FAFBFF"
            row = tk.Frame(self.list_frame, bg=row_bg)
            row.pack(fill="x", pady=5)

            if student["phone"]:
                msg = f'كل سنة وانت طيب يا {student["name"]}! 🎉🎂 ربنا يفرح قلبك ويباركك'
                ttk.Button(row, text="💬 تهنئة", style="Secondary.TButton",
                            command=lambda p=student["phone"], m=msg: open_whatsapp(p, m)).pack(side="left", padx=10)

            when = "اليوم! 🎉" if is_today else f"بعد {delta} يوم/أيام"
            tk.Label(row, text=f'🎂  {student["name"]}', font=FONTS["body_bold"],
                      bg=row_bg, fg=COLORS["text_main"], anchor="e").pack(side="right", padx=14, pady=10)
            tk.Label(row, text=f'{bd_date.strftime("%Y-%m-%d")}   ({when})', font=FONTS["small"],
                      bg=row_bg, fg=COLORS["warning"] if is_today else COLORS["text_muted"]
                      ).pack(side="right", padx=4, pady=10)


# =========================================================
# صفحة: الآية اليومية
# =========================================================
class VersePage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        self._build_ui()

    def _build_ui(self):
        page_header(self, "الآية اليومية", "آية تتغيّر تلقائيًا كل يوم")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # بطاقة عرض آية اليوم
        verse_outer, verse_card = card(body)
        verse_outer.pack(fill="x", pady=(0, 16))
        verse_pad = tk.Frame(verse_card, bg=COLORS["primary_light"])
        verse_pad.pack(fill="both", expand=True, padx=1, pady=1)

        self.verse_label = tk.Label(verse_pad, text="", font=FONTS["verse"], wraplength=750,
                                      justify="center", bg=COLORS["primary_light"], fg=COLORS["text_main"],
                                      pady=36, padx=20)
        self.verse_label.pack(fill="x")
        self.ref_label = tk.Label(verse_pad, text="", font=FONTS["verse_ref"], bg=COLORS["primary_light"],
                                    fg=COLORS["primary"], padx=20)
        self.ref_label.pack(pady=(0, 20))

        # بطاقة إضافة آية جديدة
        add_outer, add_card = card(body)
        add_outer.pack(fill="x")
        tk.Label(add_card, text="إضافة آية جديدة لبنك الآيات", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(fill="x", padx=20, pady=(18, 6))

        add_pad = tk.Frame(add_card, bg=COLORS["card_bg"])
        add_pad.pack(fill="x", padx=20, pady=(0, 18))

        ttk.Label(add_pad, text="نص الآية", style="Body.TLabel").grid(row=0, column=1, sticky="e", padx=6, pady=6)
        self.verse_var = tk.StringVar()
        ttk.Entry(add_pad, textvariable=self.verse_var, style="App.TEntry", width=55).grid(row=0, column=0, padx=6, sticky="w")

        ttk.Label(add_pad, text="المرجع", style="Body.TLabel").grid(row=1, column=1, sticky="e", padx=6, pady=6)
        self.ref_var = tk.StringVar()
        ttk.Entry(add_pad, textvariable=self.ref_var, style="App.TEntry", width=30).grid(row=1, column=0, padx=6, sticky="w")

        ttk.Button(add_pad, text="➕ إضافة", style="Primary.TButton",
                    command=self.add_verse).grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

    def refresh(self):
        v = db.get_verse_of_the_day()
        if v:
            self.verse_label.config(text=v["verse_text"])
            self.ref_label.config(text=v["reference"] or "")
        else:
            self.verse_label.config(text="لا توجد آيات مضافة بعد.")
            self.ref_label.config(text="")

    def add_verse(self):
        if not self.verse_var.get().strip():
            messagebox.showwarning("تنبيه", "الرجاء إدخال نص الآية")
            return
        db.add_verse(self.verse_var.get().strip(), self.ref_var.get().strip())
        self.verse_var.set("")
        self.ref_var.set("")
        self.refresh()
        messagebox.showinfo("تم", "تمت إضافة الآية إلى البنك")


# =========================================================
# صفحة: التقارير والإحصائيات
# =========================================================
class ReportsPage(tk.Frame):
    def __init__(self, parent, locked_stage_id=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.locked_stage_id = locked_stage_id
        self.stage_choices = []
        self.chart_canvas_widget = None
        self._build_ui()

    def _build_ui(self):
        page_header(self, "التقارير والإحصائيات", "تصدير تقارير إكسل، ومتابعة نسب الحضور")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # بطاقة الفلتر والتصدير
        top_outer, top_card = card(body)
        top_outer.pack(fill="x", pady=(0, 16))
        top_pad = tk.Frame(top_card, bg=COLORS["card_bg"])
        top_pad.pack(fill="x", padx=20, pady=18)

        filter_row = tk.Frame(top_pad, bg=COLORS["card_bg"])
        filter_row.pack(fill="x", pady=(0, 12))
        self.stage_var = tk.StringVar()
        self.stage_combo = ttk.Combobox(filter_row, textvariable=self.stage_var, style="App.TCombobox",
                                          width=22, state="readonly")
        self.stage_combo.pack(side="right")
        self.stage_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(filter_row, text="المرحلة:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        btn_row = tk.Frame(top_pad, bg=COLORS["card_bg"])
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="📊 تصدير تقرير الحضور (Excel)", style="Primary.TButton",
                    command=self.export_attendance).pack(side="right", padx=4)
        ttk.Button(btn_row, text="📞 تصدير أرقام الهواتف (Excel)", style="Secondary.TButton",
                    command=self.export_phones).pack(side="right", padx=4)
        ttk.Button(btn_row, text="📄 تصدير الإحصائيات (PDF)", style="Secondary.TButton",
                    command=self.export_stats_pdf).pack(side="right", padx=4)

        # بطاقة أكثر المخدومين انتظامًا
        top_students_outer, top_students_card = card(body)
        top_students_outer.pack(fill="x", pady=(0, 16))
        self.top_students_pad = tk.Frame(top_students_card, bg=COLORS["card_bg"])
        self.top_students_pad.pack(fill="x", padx=20, pady=18)

        # بطاقة الرسم البياني
        chart_outer, chart_card = card(body)
        chart_outer.pack(fill="both", expand=True)
        self.chart_pad = tk.Frame(chart_card, bg=COLORS["card_bg"])
        self.chart_pad.pack(fill="both", expand=True, padx=20, pady=18)

    def _selected_stage_id(self):
        if self.locked_stage_id is not None:
            return self.locked_stage_id
        label = self.stage_var.get()
        for lbl, sid in self.stage_choices:
            if lbl == label:
                return sid
        return None

    def refresh(self):
        if self.locked_stage_id is not None:
            stages = db.get_all_stages()
            name = next((s["name"] for s in stages if s["id"] == self.locked_stage_id), "مرحلتي")
            self.stage_choices = [(name, self.locked_stage_id)]
            self.stage_combo["values"] = [name]
            self.stage_var.set(name)
            self.stage_combo.configure(state="disabled")
        else:
            self.stage_choices = get_stage_choices(include_all=True, include_unset=True)
            current = self.stage_var.get()
            self.stage_combo["values"] = [c[0] for c in self.stage_choices]
            if current not in self.stage_combo["values"]:
                self.stage_var.set(self.stage_choices[0][0])

        stage_id = self._selected_stage_id()
        stats = db.get_attendance_stats(stage_id=stage_id, min_sessions=2)

        # أكثر المخدومين انتظامًا (أعلى 5)
        for w in self.top_students_pad.winfo_children():
            w.destroy()
        tk.Label(self.top_students_pad, text="🏆 الأكثر انتظامًا", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(fill="x", pady=(0, 8))
        if not stats:
            tk.Label(self.top_students_pad, text="لا توجد بيانات حضور كافية بعد (يلزم جلستان على الأقل لكل مخدوم).",
                      font=FONTS["small"], bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="e")
        else:
            for s in stats[:5]:
                row = tk.Frame(self.top_students_pad, bg=COLORS["card_bg"])
                row.pack(fill="x", pady=2)
                tk.Label(row, text=f'{s["percentage"]}%', font=FONTS["body_bold"], bg=COLORS["card_bg"],
                          fg=COLORS["success"]).pack(side="left")
                tk.Label(row, text=f'{s["name"]}  ({s["present_count"]}/{s["total_sessions"]})',
                          font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["text_main"],
                          anchor="e").pack(side="right", fill="x", expand=True)

        # الرسم البياني
        for w in self.chart_pad.winfo_children():
            w.destroy()
        tk.Label(self.chart_pad, text="📈 نسبة الحضور لكل مخدوم", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(fill="x", pady=(0, 8))

        if not stats:
            tk.Label(self.chart_pad, text="لا توجد بيانات كافية لعرض الرسم البياني بعد.",
                      font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(pady=20)
            return

        try:
            import matplotlib
            matplotlib.use("Agg")  # سيتم استبداله بـ TkAgg عبر FigureCanvasTkAgg أدناه
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            import matplotlib.font_manager as fm

            top_stats = stats[:12]
            names = [s["name"] for s in top_stats][::-1]
            pcts = [s["percentage"] for s in top_stats][::-1]

            fig = Figure(figsize=(6, max(2.5, 0.35 * len(names))), dpi=100)
            ax = fig.add_subplot(111)
            bars = ax.barh(range(len(names)), pcts, color="#4F5DFF")
            ax.set_xlim(0, 100)
            ax.set_yticks(range(len(names)))
            ax.set_yticklabels(names, fontsize=9)
            ax.set_xlabel("%")
            for i, v in enumerate(pcts):
                ax.text(v + 1, i, f"{v}%", va="center", fontsize=8)
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=self.chart_pad)
            canvas.draw()
            widget = canvas.get_tk_widget()
            widget.pack(fill="both", expand=True)
            self.chart_canvas_widget = widget
        except Exception as e:
            tk.Label(self.chart_pad, text=f"تعذر رسم الرسم البياني: {e}",
                      font=FONTS["small"], bg=COLORS["card_bg"], fg=COLORS["danger"]).pack(pady=10)

    def export_attendance(self):
        filepath = filedialog.asksaveasfilename(
            title="حفظ تقرير الحضور", defaultextension=".xlsx",
            filetypes=[("ملفات إكسل", "*.xlsx")], initialfile="تقرير_الحضور.xlsx"
        )
        if not filepath:
            return
        try:
            db.export_attendance_report(filepath, stage_id=self._selected_stage_id())
            messagebox.showinfo("تم", "تم حفظ تقرير الحضور بنجاح")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر حفظ التقرير: {e}")

    def export_phones(self):
        filepath = filedialog.asksaveasfilename(
            title="حفظ قائمة الهواتف", defaultextension=".xlsx",
            filetypes=[("ملفات إكسل", "*.xlsx")], initialfile="أرقام_الهواتف.xlsx"
        )
        if not filepath:
            return
        try:
            db.export_phone_list(filepath, stage_id=self._selected_stage_id())
            messagebox.showinfo("تم", "تم حفظ قائمة الهواتف بنجاح")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر حفظ القائمة: {e}")

    def export_stats_pdf(self):
        stage_label = self.stage_var.get() or "كل المراحل"
        filepath = filedialog.asksaveasfilename(
            title="حفظ إحصائيات الحضور", defaultextension=".pdf",
            filetypes=[("ملفات PDF", "*.pdf")], initialfile="إحصائيات_الحضور.pdf"
        )
        if not filepath:
            return
        try:
            db.export_stats_pdf(filepath, stage_id=self._selected_stage_id(), stage_label=stage_label)
            messagebox.showinfo("تم", "تم حفظ الإحصائيات بنجاح")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر حفظ الملف: {e}")


# =========================================================
# صفحة: الخطة السنوية
# =========================================================
class LessonsPage(tk.Frame):
    def __init__(self, parent, locked_stage_id=None, username=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.locked_stage_id = locked_stage_id
        self.username = username
        self.stage_choices = []
        self._build_ui()

    def _build_ui(self):
        page_header(self, "الخطة السنوية", "خطة الدروس الأسبوعية لكل مرحلة ومتابعة ما تم تغطيته")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        form_outer, form_card = card(body)
        form_outer.pack(fill="x", pady=(0, 16))
        form_pad = tk.Frame(form_card, bg=COLORS["card_bg"])
        form_pad.pack(fill="x", padx=20, pady=18)

        filter_row = tk.Frame(form_pad, bg=COLORS["card_bg"])
        filter_row.pack(fill="x", pady=(0, 12))
        ttk.Button(filter_row, text="📄 تصدير PDF", style="Secondary.TButton",
                    command=self.export_pdf).pack(side="left")
        self.stage_var = tk.StringVar()
        self.stage_combo = ttk.Combobox(filter_row, textvariable=self.stage_var, style="App.TCombobox",
                                          width=22, state="readonly")
        self.stage_combo.pack(side="right")
        self.stage_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(filter_row, text="المرحلة:", style="Body.TLabel").pack(side="right", padx=(0, 8))

        add_row = tk.Frame(form_pad, bg=COLORS["card_bg"])
        add_row.pack(fill="x")
        ttk.Button(add_row, text="➕ إضافة درس", style="Primary.TButton",
                    command=self.add_lesson).pack(side="right", padx=(8, 0))
        self.week_date_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.week_date_var, style="App.TEntry", width=14
                   ).pack(side="right", padx=6)
        ttk.Label(add_row, text="تاريخ الأسبوع", style="Body.TLabel").pack(side="right", padx=(6, 0))
        self.title_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.title_var, style="App.TEntry", width=40
                   ).pack(side="right", padx=6, fill="x", expand=True)
        ttk.Label(add_row, text="عنوان الدرس", style="Body.TLabel").pack(side="right", padx=(6, 0))

        list_outer, list_card = card(body)
        list_outer.pack(fill="both", expand=True)
        list_pad = tk.Frame(list_card, bg=COLORS["card_bg"])
        list_pad.pack(fill="both", expand=True, padx=20, pady=20)
        self.list_container = tk.Frame(list_pad, bg=COLORS["card_bg"])
        self.list_container.pack(fill="both", expand=True)

    def _selected_stage_id(self):
        if self.locked_stage_id is not None:
            return self.locked_stage_id
        label = self.stage_var.get()
        for lbl, sid in self.stage_choices:
            if lbl == label:
                return sid
        return None

    def refresh(self):
        if self.locked_stage_id is not None:
            stages = db.get_all_stages()
            name = next((s["name"] for s in stages if s["id"] == self.locked_stage_id), "مرحلتي")
            self.stage_choices = [(name, self.locked_stage_id)]
            self.stage_combo["values"] = [name]
            self.stage_var.set(name)
            self.stage_combo.configure(state="disabled")
        else:
            self.stage_choices = get_stage_choices(include_all=False, include_unset=False)
            current = self.stage_var.get()
            self.stage_combo["values"] = [c[0] for c in self.stage_choices]
            if current not in self.stage_combo["values"] and self.stage_choices:
                self.stage_var.set(self.stage_choices[0][0])

        stage_id = self._selected_stage_id()

        for w in self.list_container.winfo_children():
            w.destroy()

        if stage_id is None:
            tk.Label(self.list_container, text="أضف مرحلة أولًا من صفحة المراحل حتى تقدر تضيف خطة دروس.",
                      font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(pady=10)
            return

        lessons = db.get_lessons(stage_id=stage_id)
        if not lessons:
            tk.Label(self.list_container, text="لا توجد دروس مضافة لهذه المرحلة بعد.",
                      font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(pady=10)
            return

        for i, lesson in enumerate(lessons):
            row_bg = "#FAFBFF" if i % 2 else COLORS["card_bg"]
            row = tk.Frame(self.list_container, bg=row_bg)
            row.pack(fill="x", pady=1)

            ttk.Button(row, text="حذف", style="Danger.TButton",
                        command=lambda lid=lesson["id"]: self.delete_lesson(lid)).pack(side="left", padx=8, pady=6)

            covered_var = tk.IntVar(value=lesson["covered"])
            chk = ttk.Checkbutton(row, text="تم", variable=covered_var, style="App.TCheckbutton",
                                    command=lambda lid=lesson["id"], v=covered_var: self.toggle_covered(lid, v))
            chk.pack(side="left", padx=8)

            text_col = tk.Frame(row, bg=row_bg)
            text_col.pack(side="right", fill="x", expand=True, padx=10, pady=6)
            title_color = COLORS["text_muted"] if lesson["covered"] else COLORS["text_main"]
            tk.Label(text_col, text=lesson["title"], font=FONTS["body_bold"], bg=row_bg,
                      fg=title_color, anchor="e").pack(fill="x")
            if lesson["week_date"]:
                tk.Label(text_col, text=lesson["week_date"], font=FONTS["small"], bg=row_bg,
                          fg=COLORS["text_muted"], anchor="e").pack(fill="x")

    def add_lesson(self):
        stage_id = self._selected_stage_id()
        if stage_id is None:
            messagebox.showwarning("تنبيه", "اختر مرحلة أولًا")
            return
        if not self.title_var.get().strip():
            messagebox.showwarning("تنبيه", "الرجاء إدخال عنوان الدرس")
            return
        db.add_lesson(stage_id, self.title_var.get().strip(), self.week_date_var.get().strip())
        if self.username:
            db.log_activity(self.username, "إضافة درس", self.title_var.get().strip())
        self.title_var.set("")
        self.week_date_var.set("")
        self.refresh()

    def toggle_covered(self, lesson_id, var):
        db.toggle_lesson_covered(lesson_id, bool(var.get()))
        self.refresh()

    def delete_lesson(self, lesson_id):
        if messagebox.askyesno("تأكيد", "هل تريد حذف هذا الدرس؟"):
            db.delete_lesson(lesson_id)
            if self.username:
                db.log_activity(self.username, "حذف درس", f"id={lesson_id}")
            self.refresh()

    def export_pdf(self):
        stage_id = self._selected_stage_id()
        if stage_id is None:
            messagebox.showwarning("تنبيه", "اختر مرحلة أولًا")
            return
        stage_label = self.stage_var.get()
        filepath = filedialog.asksaveasfilename(
            title="حفظ الخطة السنوية", defaultextension=".pdf",
            filetypes=[("ملفات PDF", "*.pdf")], initialfile="الخطة_السنوية.pdf"
        )
        if not filepath:
            return
        try:
            db.export_lessons_pdf(filepath, stage_id, stage_label)
            messagebox.showinfo("تم", "تم حفظ الخطة السنوية بنجاح")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر حفظ الملف: {e}")


# =========================================================
# صفحة: المستخدمون (أدمن فقط)
# =========================================================
class UsersPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        self.stage_choices = []
        self.user_class_choices = []
        self._build_ui()

    def _build_ui(self):
        page_header(self, "المستخدمون", "إدارة حسابات الدخول: أدمن (كل المراحل) أو خادم (مرحلة واحدة)")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        form_outer, form_card = card(body)
        form_outer.pack(fill="x", pady=(0, 16))
        tk.Label(form_card, text="إضافة مستخدم جديد", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(fill="x", padx=20, pady=(18, 6))

        form_pad = tk.Frame(form_card, bg=COLORS["card_bg"])
        form_pad.pack(fill="x", padx=20, pady=(0, 18))

        ttk.Label(form_pad, text="اسم المستخدم", style="Body.TLabel").grid(row=0, column=3, sticky="e", padx=6, pady=6)
        self.username_var = tk.StringVar()
        ttk.Entry(form_pad, textvariable=self.username_var, style="App.TEntry", width=20).grid(row=0, column=2, padx=6)

        ttk.Label(form_pad, text="كلمة المرور", style="Body.TLabel").grid(row=0, column=1, sticky="e", padx=6)
        self.password_var = tk.StringVar()
        ttk.Entry(form_pad, textvariable=self.password_var, style="App.TEntry", width=20, show="*").grid(row=0, column=0, padx=6)

        ttk.Label(form_pad, text="الصلاحية", style="Body.TLabel").grid(row=1, column=3, sticky="e", padx=6, pady=6)
        self.role_var = tk.StringVar(value="خادم (مرحلة واحدة)")
        role_combo = ttk.Combobox(form_pad, textvariable=self.role_var, style="App.TCombobox", width=22,
                                    state="readonly", values=["أدمن (كل المراحل)", "خادم (مرحلة واحدة)"])
        role_combo.grid(row=1, column=2, padx=6, sticky="w")
        role_combo.bind("<<ComboboxSelected>>", lambda e: self._toggle_stage_field())

        ttk.Label(form_pad, text="المرحلة (للخادم فقط)", style="Body.TLabel").grid(row=1, column=1, sticky="e", padx=6)
        self.user_stage_var = tk.StringVar()
        self.user_stage_combo = ttk.Combobox(form_pad, textvariable=self.user_stage_var, style="App.TCombobox",
                                               width=20, state="readonly")
        self.user_stage_combo.grid(row=1, column=0, padx=6)
        self.user_stage_combo.bind("<<ComboboxSelected>>", lambda e: self._reload_user_class_choices())

        ttk.Label(form_pad, text="الفصل (اختياري - اتركه لكل الفصول)", style="Body.TLabel").grid(row=2, column=1, sticky="e", padx=6, pady=6)
        self.user_class_var = tk.StringVar()
        self.user_class_combo = ttk.Combobox(form_pad, textvariable=self.user_class_var, style="App.TCombobox",
                                               width=20, state="readonly")
        self.user_class_combo.grid(row=2, column=0, padx=6)

        ttk.Button(form_pad, text="➕ إضافة مستخدم", style="Primary.TButton",
                    command=self.add_user).grid(row=3, column=0, columnspan=4, sticky="e", pady=(12, 0))

        # بطاقة النسخ الاحتياطي
        backup_outer, backup_card = card(body)
        backup_outer.pack(fill="x", pady=(0, 16))
        backup_pad = tk.Frame(backup_card, bg=COLORS["card_bg"])
        backup_pad.pack(fill="x", padx=20, pady=18)
        tk.Label(backup_pad, text="💾 النسخ الاحتياطي", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"], anchor="e").pack(fill="x", pady=(0, 8))
        tk.Label(backup_pad, text="يأخذ البرنامج نسخة احتياطية تلقائيًا عند إغلاقه. يمكنك استرجاع نسخة قديمة لو حصلت مشكلة في البيانات.",
                  font=FONTS["small"], bg=COLORS["card_bg"], fg=COLORS["text_muted"], anchor="e",
                  wraplength=800, justify="right").pack(fill="x", pady=(0, 10))
        backup_btn_row = tk.Frame(backup_pad, bg=COLORS["card_bg"])
        backup_btn_row.pack(fill="x")
        ttk.Button(backup_btn_row, text="💾 أخذ نسخة احتياطية الآن", style="Secondary.TButton",
                    command=self.take_backup_now).pack(side="right", padx=4)
        ttk.Button(backup_btn_row, text="♻️ استرجاع نسخة احتياطية", style="Danger.TButton",
                    command=self.restore_backup).pack(side="right", padx=4)

        list_outer, list_card = card(body)
        list_outer.pack(fill="both", expand=True)
        list_pad = tk.Frame(list_card, bg=COLORS["card_bg"])
        list_pad.pack(fill="both", expand=True, padx=20, pady=20)
        self.list_container = tk.Frame(list_pad, bg=COLORS["card_bg"])
        self.list_container.pack(fill="both", expand=True)

    def take_backup_now(self):
        try:
            path = db.backup_database()
            messagebox.showinfo("تم", f"تم أخذ نسخة احتياطية بنجاح:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر أخذ نسخة احتياطية: {e}")

    def restore_backup(self):
        backups = db.list_backups()
        if not backups:
            messagebox.showinfo("تنبيه", "لا توجد نسخ احتياطية محفوظة بعد.")
            return

        win = tk.Toplevel(self)
        win.title("استرجاع نسخة احتياطية")
        win.geometry("450x450")
        win.configure(bg=COLORS["bg"])
        tk.Label(win, text="♻️ اختر نسخة احتياطية للاسترجاع", font=FONTS["h2"],
                  bg=COLORS["bg"], fg=COLORS["text_main"]).pack(pady=14)
        tk.Label(win, text="⚠️ سيتم استبدال البيانات الحالية. البرنامج سيحتاج إعادة تشغيل بعدها.",
                  font=FONTS["small"], bg=COLORS["bg"], fg=COLORS["danger"],
                  wraplength=400, justify="center").pack(pady=(0, 10))

        list_frame = tk.Frame(win, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        def do_restore(path):
            if messagebox.askyesno("تأكيد نهائي", "هل أنت متأكد من استرجاع هذه النسخة؟ لازم تقفل البرنامج وتفتحه تاني بعدها."):
                try:
                    db.restore_from_backup(path)
                    messagebox.showinfo("تم", "تم الاسترجاع بنجاح. الرجاء إغلاق البرنامج وإعادة تشغيله الآن.")
                    win.destroy()
                except Exception as e:
                    messagebox.showerror("خطأ", f"تعذر الاسترجاع: {e}")

        for i, path in enumerate(backups):
            row_bg = "#FAFBFF" if i % 2 else "#FFFFFF"
            row = tk.Frame(list_frame, bg=row_bg)
            row.pack(fill="x", pady=1)
            ttk.Button(row, text="استرجاع", style="Danger.TButton",
                        command=lambda p=path: do_restore(p)).pack(side="left", padx=8, pady=6)
            fname = os.path.basename(path)
            tk.Label(row, text=fname, font=FONTS["small"], bg=row_bg, fg=COLORS["text_main"],
                      anchor="e").pack(side="right", padx=10, fill="x", expand=True)

    def _toggle_stage_field(self):
        if self.role_var.get().startswith("أدمن"):
            self.user_stage_combo.configure(state="disabled")
            self.user_class_combo.configure(state="disabled")
            self.user_class_var.set("")
        else:
            self.user_stage_combo.configure(state="readonly")
            self.user_class_combo.configure(state="readonly")
            self._reload_user_class_choices()

    def _reload_user_class_choices(self):
        """يعيد تحميل قايمة الفصول بناءً على المرحلة المختارة حاليًا في نموذج إضافة المستخدم."""
        if self.role_var.get().startswith("أدمن"):
            return
        label = self.user_stage_var.get()
        stage_id = next((sid for lbl, sid in self.stage_choices if lbl == label), None)
        classes = db.get_distinct_classes(stage_id=stage_id) if stage_id is not None else []
        self.user_class_choices = [("كل فصول المرحلة", None)] + [(c, c) for c in classes]
        self.user_class_combo["values"] = [c[0] for c in self.user_class_choices]
        self.user_class_var.set("كل فصول المرحلة")

    def refresh(self):
        self.stage_choices = get_stage_choices(include_all=False, include_unset=False)
        self.user_stage_combo["values"] = [c[0] for c in self.stage_choices]
        if self.stage_choices and not self.user_stage_var.get():
            self.user_stage_var.set(self.stage_choices[0][0])
        self._toggle_stage_field()

        for w in self.list_container.winfo_children():
            w.destroy()

        users = db.get_all_users()
        admins_count = sum(1 for u in users if u["role"] == "admin")
        for i, u in enumerate(users):
            row_bg = "#FAFBFF" if i % 2 else COLORS["card_bg"]
            row = tk.Frame(self.list_container, bg=row_bg)
            row.pack(fill="x", pady=1)

            is_last_admin = u["role"] == "admin" and admins_count <= 1
            del_btn = ttk.Button(row, text="حذف", style="Danger.TButton",
                                   command=lambda uid=u["id"]: self.delete_user(uid))
            del_btn.pack(side="left", padx=8, pady=6)
            if is_last_admin:
                del_btn.configure(state="disabled")

            ttk.Button(row, text="🔑 إعادة تعيين كلمة المرور", style="Secondary.TButton",
                        command=lambda uid=u["id"], name=u["username"]: self.reset_password(uid, name)
                        ).pack(side="left", padx=8, pady=6)

            if u["role"] == "admin":
                role_text = "أدمن"
            else:
                stage_part = u["stage_name"] or "بدون مرحلة"
                role_text = f'خادم ({stage_part} - {u["class_name"]})' if u["class_name"] else f'خادم ({stage_part})'
            tk.Label(row, text=role_text, font=FONTS["small"], bg=row_bg,
                      fg=COLORS["text_muted"]).pack(side="right", padx=(0, 14), pady=8)
            tk.Label(row, text=f'👤 {u["username"]}', font=FONTS["body_bold"], bg=row_bg,
                      fg=COLORS["text_main"], anchor="e").pack(side="right", padx=10, pady=8)

    def add_user(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم المستخدم وكلمة المرور")
            return
        is_admin = self.role_var.get().startswith("أدمن")
        stage_id = None
        class_name = None
        if not is_admin:
            label = self.user_stage_var.get()
            stage_id = next((sid for lbl, sid in self.stage_choices if lbl == label), None)
            if stage_id is None:
                messagebox.showwarning("تنبيه", "اختر مرحلة للخادم")
                return
            class_label = self.user_class_var.get()
            class_name = next((val for lbl, val in getattr(self, "user_class_choices", []) if lbl == class_label), None)
        ok, msg = db.create_user(username, password, role="admin" if is_admin else "servant",
                                    stage_id=stage_id, class_name=class_name)
        if not ok:
            messagebox.showerror("خطأ", msg)
            return
        self.username_var.set("")
        self.password_var.set("")
        self.refresh()

    def reset_password(self, user_id, username):
        new_password = simpledialog.askstring("إعادة تعيين كلمة المرور",
                                                f"كلمة المرور الجديدة لـ {username}:", show="*")
        if new_password:
            db.reset_user_password(user_id, new_password)
            messagebox.showinfo("تم", "تم تغيير كلمة المرور بنجاح")

    def delete_user(self, user_id):
        if messagebox.askyesno("تأكيد", "هل تريد حذف هذا المستخدم؟"):
            db.delete_user(user_id)
            self.refresh()


# =========================================================
# صفحة: سجل النشاط (أدمن فقط)
# =========================================================
class ActivityLogPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        self._build_ui()

    def _build_ui(self):
        page_header(self, "سجل النشاط", "من أضاف/عدّل/حذف إيه ومتى")

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        top = tk.Frame(body, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="🔄 تحديث", style="Secondary.TButton", command=self.refresh).pack(side="left")

        outer, inner = card(body)
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(inner, bg=COLORS["card_bg"])
        pad.pack(fill="both", expand=True, padx=16, pady=16)

        columns = ("time", "username", "action", "details")
        self.tree = ttk.Treeview(pad, columns=columns, show="headings", height=20, style="App.Treeview")
        headings = {"time": "الوقت", "username": "المستخدم", "action": "الإجراء", "details": "تفاصيل"}
        widths = {"time": 150, "username": 120, "action": 160, "details": 300}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, anchor="center", width=widths[col])
        self.tree.tag_configure("odd", background="#FAFBFF")
        self.tree.tag_configure("even", background="#FFFFFF")
        self.tree.pack(fill="both", expand=True)

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, entry in enumerate(db.get_recent_activity(limit=300)):
            tag = "odd" if i % 2 else "even"
            self.tree.insert("", "end", values=(
                entry["timestamp"], entry["username"] or "-", entry["action"], entry["details"] or ""
            ), tags=(tag,))


# =========================================================
# شاشة تسجيل الدخول
# =========================================================
class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("تسجيل الدخول - متابعة المخدومين")
        self.geometry("440x560")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])
        setup_styles(self)
        self.result_user = None

        outer, inner = card(self)
        outer.pack(expand=True, padx=40, pady=40, fill="both")
        pad = tk.Frame(inner, bg=COLORS["card_bg"])
        pad.pack(expand=True, fill="both", padx=30, pady=30)

        tk.Label(pad, text="⛪", font=("Segoe UI", 40), bg=COLORS["card_bg"]).pack(pady=(10, 0))
        tk.Label(pad, text="برنامج متابعة المخدومين", font=FONTS["h2"], bg=COLORS["card_bg"],
                  fg=COLORS["text_main"]).pack(pady=(6, 20))

        ttk.Label(pad, text="رابط السيرفر", style="Body.TLabel").pack(anchor="e")
        self.server_var = tk.StringVar(value=db.load_config() or "")
        server_entry = ttk.Entry(pad, textvariable=self.server_var, style="App.TEntry", width=30, justify="left")
        server_entry.pack(fill="x", pady=(4, 12))

        ttk.Label(pad, text="اسم المستخدم", style="Body.TLabel").pack(anchor="e")
        self.username_var = tk.StringVar()
        entry1 = ttk.Entry(pad, textvariable=self.username_var, style="App.TEntry", width=30, justify="right")
        entry1.pack(fill="x", pady=(4, 12))

        ttk.Label(pad, text="كلمة المرور", style="Body.TLabel").pack(anchor="e")
        self.password_var = tk.StringVar()
        entry2 = ttk.Entry(pad, textvariable=self.password_var, style="App.TEntry", width=30, show="*", justify="right")
        entry2.pack(fill="x", pady=(4, 6))
        entry2.bind("<Return>", lambda e: self.try_login())

        self.error_label = tk.Label(pad, text="", font=FONTS["small"], bg=COLORS["card_bg"], fg=COLORS["danger"])
        self.error_label.pack(pady=(0, 6))

        ttk.Button(pad, text="تسجيل الدخول", style="Primary.TButton",
                    command=self.try_login).pack(fill="x", pady=(10, 0))

        tk.Label(pad, text="أول مرة؟ حط رابط السيرفر، واستخدم admin / admin ثم غيّرها من صفحة المستخدمين",
                  font=FONTS["small"], bg=COLORS["card_bg"], fg=COLORS["text_muted"],
                  wraplength=280, justify="center").pack(pady=(16, 0))

        entry1.focus_set()

    def try_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self.error_label.config(text="الرجاء إدخال اسم المستخدم وكلمة المرور")
            return
        server_url = db.normalize_url(self.server_var.get())
        if not server_url:
            self.error_label.config(text="الرجاء إدخال رابط السيرفر")
            return
        db.save_config(server_url)
        self.error_label.config(text="جارِ الاتصال بالسيرفر...", fg=COLORS["text_muted"])
        self.update_idletasks()
        try:
            user = db.verify_login(username, password)
        except ApiError as e:
            self.error_label.config(text=e.message, fg=COLORS["danger"])
            return
        if not user:
            self.error_label.config(text="اسم المستخدم أو كلمة المرور غير صحيحة", fg=COLORS["danger"])
            return
        self.result_user = user
        self.destroy()


if __name__ == "__main__":
    db.init_db()

    login = LoginWindow()
    login.mainloop()

    if login.result_user is not None:
        app = MokhdomeenApp(current_user=login.result_user)
        app.mainloop()
