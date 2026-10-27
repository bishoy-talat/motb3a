# -*- coding: utf-8 -*-
"""
api_client.py - عميل السيرفر لبرنامج الكمبيوتر
==============================================
بديل مباشر لملف db.py القديم: نفس أسماء الدوال ونفس شكل النتائج (قواميس dict بتتقري بـ ["key"])،
بس بدل ما يقرأ ملف قاعدة بيانات محلي، بيكلّم السيرفر الموحّد (server.py) - نفس السيرفر اللي
بيستخدمه تطبيق الموبايل، فالبيانات مشتركة وحيّة بين كل النسخ.

ملاحظة: كل الاتصالات متزامنة (synchronous) وبتحصل في نفس خيط الواجهة، فالواجهة ممكن تتجمّد
لحظات قصيرة وقت الاتصال (أطول لو الاستضافة المجانية نايمة وبتصحى).
"""

import json
import os
from datetime import date, datetime

import requests

# ---------------------- الإعدادات المحلية (رابط السيرفر) ----------------------

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".mokhdomeen_client.json")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".mokhdomeen_cache")

SERVER_URL = None   # مثال: https://your-server.example
TOKEN = None
CURRENT_USER = None
_session = requests.Session()  # بيعيد استخدام الاتصال (keep-alive) فيسرّع الطلبات المتتالية

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60   # أطول من العادي عشان الاستضافات المجانية بتاخد وقت لما تصحى من النوم

TAGS = ["", "يحتاج متابعة خاصة", "منتظم جدًا", "جديد بالخدمة"]


class ApiError(Exception):
    """أي خطأ من السيرفر أو من الاتصال. الرسالة عربية وجاهزة للعرض للمستخدم."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        self.status = status


class SessionExpired(ApiError):
    """جلسة الدخول انتهت - لازم تسجيل دخول من جديد."""


def normalize_url(url):
    """ينظّف الرابط: يضيف https:// لو ناقص (أو http:// للشبكة المحلية) ويشيل / الأخيرة."""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.lower().startswith(("http://", "https://")):
        local_prefixes = ("localhost", "127.", "192.168.", "10.", "172.")
        url = ("http://" if url.startswith(local_prefixes) else "https://") + url
    return url.rstrip("/")


def load_config():
    """يقرأ رابط السيرفر المحفوظ (لو موجود) ويرجعه."""
    global SERVER_URL
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            SERVER_URL = normalize_url(json.load(f).get("server_url", "")) or None
    except (OSError, ValueError):
        SERVER_URL = None
    return SERVER_URL


def save_config(url):
    global SERVER_URL
    SERVER_URL = normalize_url(url) or None
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"server_url": SERVER_URL}, f)
    except OSError:
        pass  # لو مقدرناش نحفظ، التطبيق يفضل شغال بالرابط الحالي في الذاكرة
    return SERVER_URL


def get_server_url():
    return SERVER_URL


# ---------------------- طبقة الطلبات ----------------------

def _stage_value(stage_id):
    """None = كل المراحل (مش بنبعت الباراميتر)، 'unset' = بدون مرحلة، أو رقم."""
    return None if stage_id is None else str(stage_id)


def _clean(params):
    return {k: v for k, v in (params or {}).items() if v is not None and v != ""}


def _request(method, path, params=None, json_body=None, files=None, stream=False):
    global TOKEN, CURRENT_USER
    if not SERVER_URL:
        raise ApiError("لم يتم إعداد رابط السيرفر بعد")
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        resp = _session.request(
            method, SERVER_URL + path, params=_clean(params), json=json_body, files=files,
            headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=stream,
        )
    except requests.exceptions.Timeout:
        raise ApiError("انتهت مهلة الاتصال بالسيرفر. لو الاستضافة مجانية ممكن تكون لسه بتصحى، جرّب تاني بعد دقيقة.")
    except requests.exceptions.RequestException:
        raise ApiError("تعذر الاتصال بالسيرفر. تأكد من الإنترنت ومن رابط السيرفر.")

    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = None
        if isinstance(detail, list):  # أخطاء التحقق التلقائية من FastAPI (422)
            detail = "بيانات غير صالحة"
        if resp.status_code == 401 and path != "/api/login":
            TOKEN = None
            CURRENT_USER = None
            raise SessionExpired(detail or "جلسة الدخول منتهية، سجّل دخول تاني", 401)
        if not detail:
            detail = f"خطأ من السيرفر ({resp.status_code})"
        raise ApiError(detail, resp.status_code)

    if stream:
        return resp
    try:
        return resp.json()
    except ValueError:
        return None


def _download(path, filepath, params=None):
    """ينزّل ملف من السيرفر ويحفظه في المسار المطلوب."""
    resp = _request("GET", path, params=params, stream=True)
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return filepath


# ---------------------- دوال محلية بحتة (نفس قواعد السيرفر بالظبط) ----------------------

def parse_flexible_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def is_valid_egyptian_phone(phone):
    phone = (phone or "").strip()
    if not phone:
        return True
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) != 11:
        return False
    return digits[:3] in ("010", "011", "012", "015")


def calculate_age(birthdate_text):
    bd = parse_flexible_date(birthdate_text)
    if bd is None:
        return None
    today = date.today()
    return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))


# ---------------------- توافق مع db.py القديم ----------------------

def init_db():
    """قاعدة البيانات دلوقتي على السيرفر، فمفيش حاجة تتعمل هنا."""


def log_activity(username, action, details=""):
    """السيرفر بيسجّل النشاط تلقائيًا مع كل عملية، فمفيش داعي نسجّله من هنا (وإلا هيتكرر)."""


# ---------------------- تسجيل الدخول ----------------------

def verify_login(username, password):
    """يرجع بيانات المستخدم لو صحيحة، None لو اسم المستخدم/كلمة المرور غلط، ويرفع ApiError لباقي المشاكل."""
    global TOKEN, CURRENT_USER
    try:
        data = _request("POST", "/api/login", json_body={"username": username, "password": password})
    except ApiError as e:
        if e.status == 401:
            return None
        raise
    TOKEN = data["token"]
    CURRENT_USER = data["user"]
    return CURRENT_USER


def logout():
    global TOKEN, CURRENT_USER
    try:
        _request("POST", "/api/logout")
    except ApiError:
        pass
    TOKEN = None
    CURRENT_USER = None


# ---------------------- المراحل ----------------------

def get_all_stages():
    return _request("GET", "/api/stages")


def add_stage(name, meeting_day=None):
    _request("POST", "/api/stages", json_body={"name": name, "meeting_day": meeting_day})


def update_stage(stage_id, new_name, meeting_day=None):
    _request("PUT", f"/api/stages/{stage_id}", json_body={"name": new_name, "meeting_day": meeting_day})


def delete_stage(stage_id):
    _request("DELETE", f"/api/stages/{stage_id}")


def count_students_in_stage(stage_id):
    return _request("GET", f"/api/stages/{stage_id}/student_count")["count"]


def get_distinct_classes(stage_id=None):
    return _request("GET", "/api/classes", params={"stage_id": _stage_value(stage_id)})


# ---------------------- العائلات ----------------------

def get_all_families():
    return _request("GET", "/api/families")


def get_or_create_family(name):
    name = (name or "").strip()
    if not name:
        return None
    return _request("POST", "/api/families", json_body={"name": name})["id"]


def get_family_members(family_id, exclude_student_id=None):
    return _request("GET", f"/api/families/{family_id}/members",
                    params={"exclude_student_id": exclude_student_id})


# ---------------------- المخدومون ----------------------

def get_all_students(active_only=True, stage_id=None, search="", class_name=None):
    return _request("GET", "/api/students", params={
        "stage_id": _stage_value(stage_id),
        "class_name": class_name,
        "search": search,
        "active_only": "true" if active_only else "false",
    })


def get_student(student_id):
    return _request("GET", f"/api/students/{student_id}")


def add_student(name, phone, birthdate, class_name, stage_id=None, notes="", join_date="",
                photo_path=None, family_id=None, tag=""):
    """يرجع رقم (id) المخدوم الجديد."""
    data = _request("POST", "/api/students", json_body={
        "name": name, "phone": phone, "birthdate": birthdate, "class_name": class_name,
        "stage_id": stage_id, "notes": notes, "join_date": join_date,
        "family_id": family_id, "tag": tag,
    })
    return data["id"]


def update_student(student_id, name, phone, birthdate, class_name, stage_id=None, notes="",
                   join_date="", family_id=None, tag=""):
    _request("PUT", f"/api/students/{student_id}", json_body={
        "name": name, "phone": phone, "birthdate": birthdate, "class_name": class_name,
        "stage_id": stage_id, "notes": notes, "join_date": join_date,
        "family_id": family_id, "tag": tag,
    })


def delete_student(student_id):
    _request("DELETE", f"/api/students/{student_id}")


def restore_student(student_id):
    _request("POST", f"/api/students/{student_id}/restore")


def permanently_delete_student(student_id):
    _request("DELETE", f"/api/students/{student_id}/permanent")


def get_deleted_students():
    return _request("GET", "/api/students/deleted")


def get_student_attendance_history(student_id):
    return _request("GET", f"/api/students/{student_id}/attendance_history")


def save_student_photo_file(student_id, source_filepath):
    """يرفع صورة المخدوم للسيرفر."""
    with open(source_filepath, "rb") as f:
        _request("POST", f"/api/students/{student_id}/photo",
                 files={"file": (os.path.basename(source_filepath), f)})


def fetch_student_photo(student_id):
    """ينزّل صورة المخدوم لمجلد مؤقت محلي ويرجع مسارها (أو None لو مفيش صورة)."""
    try:
        resp = _request("GET", f"/api/students/{student_id}/photo", stream=True)
    except ApiError as e:
        if e.status == 404:
            return None
        raise
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"student_{student_id}.img")
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return path


def import_students_from_excel(filepath):
    """يرفع ملف إكسل للسيرفر ليستورد منه المخدومين (أدمن فقط). يرجع {"imported", "skipped", "errors"}."""
    with open(filepath, "rb") as f:
        return _request("POST", "/api/students/import_excel",
                        files={"file": (os.path.basename(filepath), f)})


# ---------------------- الحضور والغياب ----------------------

def get_attendance_for_date(session_date):
    """يرجع {id المخدوم (int): حضر؟} لتاريخ معيّن."""
    data = _request("GET", "/api/attendance/map", params={"date": session_date})
    return {int(k): v for k, v in data.items()}


def save_attendance_bulk(session_date, records):
    """يحفظ حضور مجموعة مخدومين في طلب واحد. records = {id: True/False}."""
    _request("POST", "/api/attendance", json_body={
        "date": session_date,
        "records": {str(k): bool(v) for k, v in records.items()},
    })


def set_attendance(student_id, session_date, present):
    save_attendance_bulk(session_date, {student_id: present})


def get_recent_absentees_grouped(threshold=2, lookback_sessions=3, stage_id=None, class_name=None):
    # الحد (2 غياب من آخر 3 جلسات) ثابت على السيرفر عشان كل النسخ تتفق في نفس القاعدة
    return _request("GET", "/api/absentees",
                    params={"stage_id": _stage_value(stage_id), "class_name": class_name})


def get_attendance_stats(stage_id=None, class_name=None, min_sessions=1):
    return _request("GET", "/api/stats", params={
        "stage_id": _stage_value(stage_id), "class_name": class_name, "min_sessions": min_sessions,
    })


def get_stages_missing_attendance_today():
    return _request("GET", "/api/missing_attendance_today")


# ---------------------- أعياد الميلاد ولوحة المعلومات ----------------------

def _birthday_tuple(item):
    return (item["student"], datetime.strptime(item["date"], "%Y-%m-%d").date(), item["days_away"])


def get_upcoming_birthdays(days_ahead=7, stage_id=None, class_name=None):
    """يرجع قائمة tuples: (المخدوم, تاريخ عيد الميلاد القادم كـ date, عدد الأيام المتبقية)."""
    items = _request("GET", "/api/birthdays", params={
        "stage_id": _stage_value(stage_id), "class_name": class_name, "days_ahead": days_ahead,
    })
    return [_birthday_tuple(i) for i in items]


def get_dashboard_stats(stage_id=None, class_name=None):
    stats = _request("GET", "/api/dashboard",
                     params={"stage_id": _stage_value(stage_id), "class_name": class_name})
    if stats.get("nearest_birthday"):
        stats["nearest_birthday"] = _birthday_tuple(stats["nearest_birthday"])
    return stats


# ---------------------- الآية اليومية ----------------------

def get_verse_of_the_day():
    return _request("GET", "/api/verse-of-day")


def add_verse(verse_text, reference):
    _request("POST", "/api/verses", json_body={"verse_text": verse_text, "reference": reference})


# ---------------------- الخطة السنوية ----------------------

def get_lessons(stage_id=None):
    return _request("GET", "/api/lessons", params={"stage_id": _stage_value(stage_id)})


def add_lesson(stage_id, title, week_date="", notes=""):
    _request("POST", "/api/lessons", json_body={
        "stage_id": stage_id, "title": title, "week_date": week_date, "notes": notes,
    })


def toggle_lesson_covered(lesson_id, covered):
    _request("PUT", f"/api/lessons/{lesson_id}/covered", json_body={"covered": bool(covered)})


def delete_lesson(lesson_id):
    _request("DELETE", f"/api/lessons/{lesson_id}")


# ---------------------- المستخدمون وسجل النشاط (أدمن) ----------------------

def get_all_users():
    return _request("GET", "/api/users")


def create_user(username, password, role="servant", stage_id=None, class_name=None):
    """يرجع (نجح؟, رسالة) زي db.py القديم."""
    try:
        _request("POST", "/api/users", json_body={
            "username": username, "password": password, "role": role,
            "stage_id": stage_id, "class_name": class_name,
        })
        return True, ""
    except ApiError as e:
        if e.status == 400:
            return False, e.message
        raise


def update_user(user_id, role, stage_id, class_name=None):
    _request("PUT", f"/api/users/{user_id}", json_body={
        "role": role, "stage_id": stage_id, "class_name": class_name,
    })


def reset_user_password(user_id, new_password):
    _request("POST", f"/api/users/{user_id}/reset_password", json_body={"new_password": new_password})


def delete_user(user_id):
    _request("DELETE", f"/api/users/{user_id}")


def count_admins():
    return _request("GET", "/api/users/count_admins")["count"]


def get_recent_activity(limit=200):
    return _request("GET", "/api/activity_log", params={"limit": limit})


# ---------------------- التصدير (الملف بيتحفظ في المسار اللي تختاره) ----------------------

def export_attendance_report(filepath, stage_id=None, class_name=None):
    return _download("/api/export/attendance_report", filepath,
                     {"stage_id": _stage_value(stage_id), "class_name": class_name})


def export_phone_list(filepath, stage_id=None, class_name=None):
    return _download("/api/export/phone_list", filepath,
                     {"stage_id": _stage_value(stage_id), "class_name": class_name})


def export_stats_pdf(filepath, stage_id=None, stage_label="كل المراحل", class_name=None):
    return _download("/api/export/stats_pdf", filepath, {
        "stage_id": _stage_value(stage_id), "class_name": class_name, "label": stage_label,
    })


def export_lessons_pdf(filepath, stage_id, stage_name=""):
    return _download("/api/export/lessons_pdf", filepath, {"stage_id": _stage_value(stage_id)})


# ---------------------- النسخ الاحتياطي (على السيرفر، أدمن فقط) ----------------------

def backup_database():
    """يعمل نسخة احتياطية على السيرفر ويرجع اسمها."""
    return _request("POST", "/api/backup")["name"]


def list_backups():
    """أسماء النسخ الاحتياطية الموجودة على السيرفر (الأحدث أولًا)."""
    return _request("GET", "/api/backups")


def restore_from_backup(name):
    _request("POST", "/api/backup/restore", json_body={"name": os.path.basename(name)})
