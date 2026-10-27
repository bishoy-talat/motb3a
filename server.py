# -*- coding: utf-8 -*-
"""
server.py - السيرفر الموحّد لبرنامج متابعة المخدومين
=====================================================
ده الـ Backend الوحيد لكل النسخ: برنامج الكمبيوتر (Tkinter) + تطبيق الويب (PWA) + تطبيق Flutter.
كلهم بيتصلوا بنفس السيرفر ونفس قاعدة البيانات، فأي تعديل من أي نسخة بيظهر فورًا في الباقي.

المسؤوليات:
  - تسجيل الدخول بـ token + الحماية من تخمين كلمات المرور
  - فرض صلاحيات المرحلة/الفصل هنا على السيرفر نفسه (مش بس في شكل الواجهة)
  - كل العمليات (مخدومين، حضور، مراحل، خطة سنوية، مستخدمين، تقارير، نسخ احتياطي...)
  - نسخة احتياطية تلقائية يوميًا
  - تقديم ملفات تطبيق الويب (PWA)
"""

import os
import time
import secrets
import sqlite3
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

# المنطقة الزمنية: مصر (UTC+2 شتاءً و UTC+3 صيفًا) بصيغة POSIX لا تحتاج ملفات tzdata على الاستضافة.
# تقدر تغيّرها بمتغير بيئة APP_TZ. لازم تتظبط قبل أي استخدام للتاريخ/الوقت.
os.environ["TZ"] = os.environ.get("APP_TZ", "EET-2EEST,M4.5.5/0,M10.5.4/24")
try:
    time.tzset()
except AttributeError:  # ويندوز
    pass

from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel

import db

# ---------------------- نسخة احتياطية تلقائية ----------------------

def _auto_backup_loop():
    """كل ساعة نتأكد: لو آخر نسخة احتياطية أقدم من 24 ساعة، نعمل نسخة جديدة (نحتفظ بآخر 30)."""
    while True:
        try:
            backups = db.list_backups()  # الأحدث أولًا
            need_backup = True
            if backups:
                need_backup = (time.time() - os.path.getmtime(backups[0])) > 24 * 3600
            if need_backup:
                db.backup_database(keep_last=30)
        except Exception:
            pass
        time.sleep(3600)


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_auto_backup_loop, daemon=True).start()
    yield


app = FastAPI(title="متابعة المخدومين - API", lifespan=lifespan)

# التوكن بيتبعت في Header (مش cookies) فمفيش داعي لـ allow_credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webapp")

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_EXCEL_BYTES = 10 * 1024 * 1024
PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}

# ---------------------- الجلسات (Sessions) ----------------------
# تخزين في الذاكرة: token -> بيانات المستخدم. لو السيرفر اتعاد تشغيله الكل بيسجّل دخول تاني.
SESSIONS = {}
SESSION_LIFETIME = timedelta(hours=12)


def _create_session(user_row):
    token = secrets.token_hex(32)
    SESSIONS[token] = {
        "username": user_row["username"],
        "role": user_row["role"],
        "stage_id": user_row["stage_id"],
        "stage_name": user_row["stage_name"],
        "class_name": user_row["class_name"],
        "expires": datetime.now() + SESSION_LIFETIME,
    }
    return token


def _drop_sessions_for(username):
    """يلغي كل جلسات مستخدم معيّن (عند حذفه أو تغيير صلاحياته أو كلمة مروره)."""
    for tok in [t for t, s in SESSIONS.items() if s["username"] == username]:
        SESSIONS.pop(tok, None)


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="محتاج تسجيل دخول")
    token = authorization.split(" ", 1)[1]
    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="جلسة الدخول منتهية، سجّل دخول تاني")
    if session["expires"] < datetime.now():
        SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="جلسة الدخول منتهية، سجّل دخول تاني")
    return session


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="هذا الإجراء للأدمن فقط")
    return user


def stage_param(stage_id: Optional[str] = None):
    """قيمة المرحلة في الـ query: فاضي = الكل، 'unset' = بدون مرحلة، أو رقم المرحلة."""
    if stage_id in (None, ""):
        return None
    if stage_id == "unset":
        return "unset"
    try:
        return int(stage_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="قيمة المرحلة غير صالحة")


def enforce_scope(user, stage_id, class_name):
    """
    يفرض قيود المرحلة/الفصل على السيرفر نفسه بصرف النظر عمّا يرسله أي عميل.
    الأدمن: بدون قيود. الخادم: مقفول دايمًا على مرحلته (وفصله لو محدد).
    """
    if user["role"] == "admin":
        return stage_id, class_name
    if user["stage_id"] is None:
        # خادم مش مربوط بمرحلة (مثلًا المرحلة اتحذفت) - مينفعش نديله وصول مفتوح
        raise HTTPException(status_code=403, detail="حسابك غير مرتبط بمرحلة، تواصل مع الأدمن")
    return user["stage_id"], (user["class_name"] if user["class_name"] else class_name)


def get_student_in_scope(user, student_id):
    """يرجع صف المخدوم (حتى لو محذوف) لو داخل نطاق صلاحية المستخدم، وإلا 404."""
    stage_id, class_name = enforce_scope(user, None, None)
    for s in db.get_all_students(active_only=False, stage_id=stage_id, class_name=class_name):
        if s["id"] == student_id:
            return s
    raise HTTPException(status_code=404, detail="المخدوم غير موجود أو خارج نطاق صلاحيتك")


def ensure_lesson_access(user, lesson_id):
    if user["role"] == "admin":
        return
    if user["stage_id"] is None or lesson_id not in {l["id"] for l in db.get_lessons(stage_id=user["stage_id"])}:
        raise HTTPException(status_code=404, detail="الدرس غير موجود أو خارج نطاق صلاحيتك")


def public_student(row):
    """نسخة آمنة للإرسال للعميل: بدون مسار الملف الحقيقي على السيرفر (نبعت اسم الملف بس)."""
    d = dict(row)
    if d.get("photo_path"):
        d["photo_path"] = os.path.basename(d["photo_path"])
    return d


def _check_text_fields(name, phone, birthdate, class_name):
    """قواعد التحقق الموحّدة - نفس القواعد لكل النسخ (كمبيوتر/ويب/موبايل)."""
    if any(ch.isdigit() for ch in name):
        raise HTTPException(status_code=400, detail="اسم المخدوم يجب ألا يحتوي على أرقام")
    if class_name and any(ch.isdigit() for ch in class_name):
        raise HTTPException(status_code=400, detail="الفصل / المجموعة يجب ألا يحتوي على أرقام")
    if not db.is_valid_egyptian_phone(phone):
        raise HTTPException(
            status_code=400,
            detail="رقم الهاتف غير صحيح. يجب أن يكون 11 رقمًا ويبدأ بـ 010 أو 011 أو 012 أو 015",
        )
    parsed = db.parse_flexible_date(birthdate) if birthdate else None
    if birthdate and parsed is None:
        raise HTTPException(status_code=400, detail="تاريخ الميلاد غير مفهوم")
    return parsed.isoformat() if parsed else ""


def _tmp_path(suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


def _file_response(path, filename, media_type):
    """يرجع ملف مؤقت للعميل ويمسحه من السيرفر بعد الإرسال."""
    return FileResponse(path, media_type=media_type, filename=filename,
                        background=BackgroundTask(os.remove, path))


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ---------------------- نماذج البيانات (Pydantic Models) ----------------------

class LoginBody(BaseModel):
    username: str
    password: str


class StudentBody(BaseModel):
    name: str
    phone: str = ""
    birthdate: str = ""
    class_name: str = ""
    stage_id: Optional[int] = None
    notes: str = ""
    join_date: str = ""
    family_id: Optional[int] = None
    tag: str = ""


class AttendanceBody(BaseModel):
    records: dict  # {student_id (str): present (bool)}
    date: Optional[str] = None  # لو متبعتش، بيستخدم تاريخ اليوم على السيرفر


class StageBody(BaseModel):
    name: str
    meeting_day: Optional[str] = None


class FamilyBody(BaseModel):
    name: str


class VerseBody(BaseModel):
    verse_text: str
    reference: str = ""


class LessonBody(BaseModel):
    stage_id: int
    title: str
    week_date: str = ""
    notes: str = ""


class LessonCoveredBody(BaseModel):
    covered: bool


class UserCreateBody(BaseModel):
    username: str
    password: str
    role: str = "servant"
    stage_id: Optional[int] = None
    class_name: Optional[str] = None


class UserUpdateBody(BaseModel):
    role: str
    stage_id: Optional[int] = None
    class_name: Optional[str] = None


class PasswordResetBody(BaseModel):
    new_password: str


class RestoreBody(BaseModel):
    name: str


# ---------------------- حماية من تخمين كلمات المرور ----------------------
# بعد 5 محاولات غلط لنفس اسم المستخدم، الحساب بيتقفل 5 دقايق.
FAILED_LOGINS = {}
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=5)


def _check_login_lock(username: str):
    entry = FAILED_LOGINS.get(username.strip().lower())
    if entry and entry.get("locked_until") and entry["locked_until"] > datetime.now():
        remaining = int((entry["locked_until"] - datetime.now()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"محاولات دخول غلط كتير. جرّب تاني بعد {remaining} دقيقة",
        )


def _register_failed_login(username: str):
    key = username.strip().lower()
    entry = FAILED_LOGINS.setdefault(key, {"count": 0, "locked_until": None})
    if entry["locked_until"] and entry["locked_until"] <= datetime.now():
        entry["count"] = 0
        entry["locked_until"] = None
    entry["count"] += 1
    if entry["count"] >= MAX_FAILED_ATTEMPTS:
        entry["locked_until"] = datetime.now() + LOCK_DURATION


# ---------------------- تسجيل الدخول ----------------------

@app.post("/api/login")
def login(body: LoginBody):
    _check_login_lock(body.username)
    user = db.verify_login(body.username, body.password)
    if not user:
        _register_failed_login(body.username)
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    FAILED_LOGINS.pop(body.username.strip().lower(), None)
    token = _create_session(user)
    return {
        "token": token,
        "user": {
            "username": user["username"],
            "role": user["role"],
            "stage_id": user["stage_id"],
            "stage_name": user["stage_name"],
            "class_name": user["class_name"],
        },
    }


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        SESSIONS.pop(authorization.split(" ", 1)[1], None)
    return {"ok": True}


# ---------------------- المراحل والفصول ----------------------

@app.get("/api/stages")
def list_stages(user=Depends(get_current_user)):
    stages = db.get_all_stages()
    if user["role"] != "admin":
        stages = [s for s in stages if s["id"] == user["stage_id"]]
    return [{"id": s["id"], "name": s["name"], "meeting_day": s["meeting_day"],
             "student_count": db.count_students_in_stage(s["id"])} for s in stages]


@app.get("/api/classes")
def list_classes(stage_id=Depends(stage_param), user=Depends(get_current_user)):
    stage_id, _ = enforce_scope(user, stage_id, None)
    if user["role"] != "admin" and user["class_name"]:
        return [user["class_name"]]
    return db.get_distinct_classes(stage_id=stage_id)


@app.post("/api/stages")
def add_stage(body: StageBody, user=Depends(require_admin)):
    db.add_stage(body.name.strip(), body.meeting_day)
    db.log_activity(user["username"], "إضافة مرحلة", body.name.strip())
    return {"ok": True}


@app.put("/api/stages/{stage_id}")
def update_stage(stage_id: int, body: StageBody, user=Depends(require_admin)):
    db.update_stage(stage_id, body.name.strip(), body.meeting_day)
    db.log_activity(user["username"], "تعديل مرحلة", body.name.strip())
    return {"ok": True}


@app.delete("/api/stages/{stage_id}")
def delete_stage(stage_id: int, user=Depends(require_admin)):
    db.delete_stage(stage_id)
    db.log_activity(user["username"], "حذف مرحلة", f"id={stage_id}")
    return {"ok": True}


@app.get("/api/stages/{stage_id}/student_count")
def stage_student_count(stage_id: int, user=Depends(require_admin)):
    return {"count": db.count_students_in_stage(stage_id)}


# ---------------------- العائلات ----------------------

@app.get("/api/families")
def list_families(user=Depends(get_current_user)):
    return [dict(f) for f in db.get_all_families()]


@app.post("/api/families")
def add_family(body: FamilyBody, user=Depends(get_current_user)):
    return {"id": db.get_or_create_family(body.name.strip())}


@app.get("/api/families/{family_id}/members")
def family_members(family_id: int, exclude_student_id: Optional[int] = None,
                     user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, None, None)
    visible = {s["id"] for s in db.get_all_students(stage_id=stage_id, class_name=class_name)}
    return [public_student(m) for m in db.get_family_members(family_id, exclude_student_id=exclude_student_id)
            if m["id"] in visible]


# ---------------------- المخدومون ----------------------

@app.get("/api/students")
def list_students(stage_id=Depends(stage_param), class_name: Optional[str] = None, search: str = "",
                    active_only: bool = True, user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    rows = db.get_all_students(active_only=active_only, stage_id=stage_id,
                                 class_name=class_name, search=search)
    return [public_student(r) for r in rows]


@app.post("/api/students")
def add_student(body: StudentBody, user=Depends(get_current_user)):
    birthdate = _check_text_fields(body.name, body.phone, body.birthdate, body.class_name)
    stage_id, _ = enforce_scope(user, body.stage_id, None)
    class_name = body.class_name
    if user["role"] != "admin" and user["class_name"]:
        class_name = user["class_name"]
    new_id = db.add_student(body.name.strip(), body.phone.strip(), birthdate, class_name, stage_id,
                              notes=body.notes, join_date=body.join_date,
                              family_id=body.family_id, tag=body.tag)
    db.log_activity(user["username"], "إضافة مخدوم", body.name.strip())
    return {"ok": True, "id": new_id}


# ملاحظة: مسارات الأسماء الثابتة (deleted / import_excel) لازم تتعرّف قبل /{student_id}

@app.get("/api/students/deleted")
def deleted_students(user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, None, None)
    rows = db.get_deleted_students()
    if user["role"] != "admin":
        visible = {s["id"] for s in db.get_all_students(active_only=False, stage_id=stage_id,
                                                           class_name=class_name)}
        rows = [r for r in rows if r["id"] in visible]
    return [public_student(r) for r in rows]


@app.post("/api/students/import_excel")
async def import_excel(file: UploadFile = File(...), user=Depends(require_admin)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="الملف لازم يكون بصيغة .xlsx")
    content = await file.read()
    if len(content) > MAX_EXCEL_BYTES:
        raise HTTPException(status_code=413, detail="حجم الملف كبير (الحد الأقصى 10 ميجا)")
    path = _tmp_path(".xlsx")
    try:
        with open(path, "wb") as f:
            f.write(content)
        result = db.import_students_from_excel(path)
    finally:
        if os.path.exists(path):
            os.remove(path)
    db.log_activity(user["username"], "استيراد من إكسل", f"{result['imported']} مخدوم")
    return result


@app.get("/api/students/{student_id}")
def get_student(student_id: int, user=Depends(get_current_user)):
    return public_student(get_student_in_scope(user, student_id))


@app.put("/api/students/{student_id}")
def update_student(student_id: int, body: StudentBody, user=Depends(get_current_user)):
    get_student_in_scope(user, student_id)
    birthdate = _check_text_fields(body.name, body.phone, body.birthdate, body.class_name)
    stage_id, _ = enforce_scope(user, body.stage_id, None)
    class_name = body.class_name
    if user["role"] != "admin" and user["class_name"]:
        class_name = user["class_name"]
    db.update_student(student_id, body.name.strip(), body.phone.strip(), birthdate, class_name,
                        stage_id, notes=body.notes, join_date=body.join_date,
                        family_id=body.family_id, tag=body.tag)
    db.log_activity(user["username"], "تعديل مخدوم", body.name.strip())
    return {"ok": True}


@app.delete("/api/students/{student_id}")
def delete_student(student_id: int, user=Depends(get_current_user)):
    s = get_student_in_scope(user, student_id)
    db.delete_student(student_id)
    db.log_activity(user["username"], "حذف مخدوم (نقل لسلة المحذوفات)", s["name"])
    return {"ok": True}


@app.post("/api/students/{student_id}/restore")
def restore_student(student_id: int, user=Depends(get_current_user)):
    s = get_student_in_scope(user, student_id)
    db.restore_student(student_id)
    db.log_activity(user["username"], "استرجاع مخدوم", s["name"])
    return {"ok": True}


@app.delete("/api/students/{student_id}/permanent")
def permanently_delete_student(student_id: int, user=Depends(require_admin)):
    db.permanently_delete_student(student_id)
    db.log_activity(user["username"], "حذف نهائي لمخدوم", f"id={student_id}")
    return {"ok": True}


@app.get("/api/students/{student_id}/attendance_history")
def student_attendance_history(student_id: int, user=Depends(get_current_user)):
    get_student_in_scope(user, student_id)
    return [dict(r) for r in db.get_student_attendance_history(student_id)]


@app.post("/api/students/{student_id}/photo")
async def upload_photo(student_id: int, file: UploadFile = File(...), user=Depends(get_current_user)):
    get_student_in_scope(user, student_id)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in PHOTO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="صيغة الصورة غير مدعومة (png / jpg / gif / bmp)")
    content = await file.read()
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="حجم الصورة كبير (الحد الأقصى 5 ميجا)")
    path = _tmp_path(ext)
    try:
        with open(path, "wb") as f:
            f.write(content)
        db.save_student_photo_file(student_id, path)
    finally:
        if os.path.exists(path):
            os.remove(path)
    return {"ok": True}


@app.get("/api/students/{student_id}/photo")
def get_photo(student_id: int, user=Depends(get_current_user)):
    s = get_student_in_scope(user, student_id)
    path = s["photo_path"]
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="لا توجد صورة")
    return FileResponse(path)


# ---------------------- الحضور والغياب ----------------------

@app.get("/api/attendance/today")
def attendance_today(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                       user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    today_str = datetime.now().date().isoformat()
    students = db.get_all_students(stage_id=stage_id, class_name=class_name)
    existing = db.get_attendance_for_date(today_str)
    return {
        "date": today_str,
        "students": [public_student(s) for s in students],
        "existing": {str(k): bool(v) for k, v in existing.items()},
    }


@app.get("/api/attendance/map")
def attendance_map(date: Optional[str] = None, stage_id=Depends(stage_param),
                     class_name: Optional[str] = None, user=Depends(get_current_user)):
    """خريطة {id المخدوم: حضر؟} لتاريخ معيّن (الافتراضي النهاردة) - لحدود صلاحية المستخدم فقط."""
    day = datetime.now().date().isoformat()
    if date:
        parsed = db.parse_flexible_date(date)
        if parsed is None:
            raise HTTPException(status_code=400, detail="التاريخ غير مفهوم")
        day = parsed.isoformat()
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    existing = db.get_attendance_for_date(day)
    if user["role"] != "admin" or stage_id is not None or class_name is not None:
        visible = {s["id"] for s in db.get_all_students(stage_id=stage_id, class_name=class_name)}
        existing = {k: v for k, v in existing.items() if k in visible}
    return {str(k): bool(v) for k, v in existing.items()}


@app.post("/api/attendance")
def save_attendance(body: AttendanceBody, user=Depends(get_current_user)):
    day = datetime.now().date().isoformat()
    if body.date:
        parsed = db.parse_flexible_date(body.date)
        if parsed is None:
            raise HTTPException(status_code=400, detail="التاريخ غير مفهوم")
        day = parsed.isoformat()

    try:
        records = {int(k): bool(v) for k, v in body.records.items()}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="بيانات الحضور غير صالحة")

    if user["role"] != "admin":
        stage_id, class_name = enforce_scope(user, None, None)
        allowed = {s["id"] for s in db.get_all_students(stage_id=stage_id, class_name=class_name)}
        if not set(records).issubset(allowed):
            raise HTTPException(status_code=403, detail="فيه مخدومين خارج نطاق صلاحيتك")

    try:
        for student_id, present in records.items():
            db.set_attendance(student_id, day, present)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="فيه مخدوم غير موجود في البيانات")
    db.log_activity(user["username"], "تسجيل حضور", f"{day} ({len(records)} مخدوم)")
    return {"ok": True, "date": day}


@app.get("/api/absentees")
def absentees(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    return [
        {"stage_name": g["stage_name"], "class_name": g["class_name"],
         "absentees": [dict(a) for a in g["absentees"]]}
        for g in db.get_recent_absentees_grouped(threshold=2, lookback_sessions=3,
                                                    stage_id=stage_id, class_name=class_name)
    ]


@app.get("/api/stats")
def attendance_stats(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                       min_sessions: int = 1, user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    return db.get_attendance_stats(stage_id=stage_id, class_name=class_name, min_sessions=min_sessions)


@app.get("/api/missing_attendance_today")
def missing_attendance_today(user=Depends(get_current_user)):
    stages = db.get_stages_missing_attendance_today()
    if user["role"] != "admin":
        stages = [s for s in stages if s["id"] == user["stage_id"]]
    return [{"id": s["id"], "name": s["name"], "meeting_day": s["meeting_day"]} for s in stages]


# ---------------------- أعياد الميلاد ----------------------

@app.get("/api/birthdays")
def birthdays(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                days_ahead: int = 7, user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    upcoming = db.get_upcoming_birthdays(days_ahead=days_ahead, stage_id=stage_id, class_name=class_name)
    return [{"student": public_student(s), "date": bd.isoformat(), "days_away": delta}
            for s, bd, delta in upcoming]


# ---------------------- الآية اليومية ----------------------

@app.get("/api/verse-of-day")
def verse_of_day(user=Depends(get_current_user)):
    v = db.get_verse_of_the_day()
    return dict(v) if v else None


@app.get("/api/verses")
def list_verses(user=Depends(get_current_user)):
    return [dict(v) for v in db.get_all_verses()]


@app.post("/api/verses")
def add_verse(body: VerseBody, user=Depends(get_current_user)):
    db.add_verse(body.verse_text.strip(), body.reference.strip())
    return {"ok": True}


# ---------------------- الخطة السنوية ----------------------

@app.get("/api/lessons")
def list_lessons(stage_id=Depends(stage_param), user=Depends(get_current_user)):
    stage_id, _ = enforce_scope(user, stage_id, None)
    return [{**dict(l), "covered": bool(l["covered"])} for l in db.get_lessons(stage_id=stage_id)]


@app.post("/api/lessons")
def add_lesson(body: LessonBody, user=Depends(get_current_user)):
    stage_id, _ = enforce_scope(user, body.stage_id, None)
    db.add_lesson(stage_id, body.title.strip(), body.week_date.strip(), body.notes.strip())
    db.log_activity(user["username"], "إضافة درس", body.title.strip())
    return {"ok": True}


@app.put("/api/lessons/{lesson_id}/covered")
def toggle_lesson(lesson_id: int, body: LessonCoveredBody, user=Depends(get_current_user)):
    ensure_lesson_access(user, lesson_id)
    db.toggle_lesson_covered(lesson_id, body.covered)
    return {"ok": True}


@app.delete("/api/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, user=Depends(get_current_user)):
    ensure_lesson_access(user, lesson_id)
    db.delete_lesson(lesson_id)
    db.log_activity(user["username"], "حذف درس", f"id={lesson_id}")
    return {"ok": True}


# ---------------------- لوحة المعلومات ----------------------

@app.get("/api/dashboard")
def dashboard(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    stats = db.get_dashboard_stats(stage_id=stage_id, class_name=class_name)
    stats["needs_visit"] = [dict(r) for r in stats["needs_visit"]]
    if stats["nearest_birthday"]:
        s, bd, delta = stats["nearest_birthday"]
        stats["nearest_birthday"] = {"student": public_student(s), "date": bd.isoformat(), "days_away": delta}
    return stats


# ---------------------- التصدير (Excel / PDF) ----------------------

@app.get("/api/export/attendance_report")
def export_attendance_report(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                               user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    path = _tmp_path(".xlsx")
    db.export_attendance_report(path, stage_id=stage_id, class_name=class_name)
    return _file_response(path, "attendance_report.xlsx", XLSX_MIME)


@app.get("/api/export/phone_list")
def export_phone_list(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                        user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    path = _tmp_path(".xlsx")
    db.export_phone_list(path, stage_id=stage_id, class_name=class_name)
    return _file_response(path, "phone_list.xlsx", XLSX_MIME)


@app.get("/api/export/stats_pdf")
def export_stats_pdf(stage_id=Depends(stage_param), class_name: Optional[str] = None,
                       label: str = "كل المراحل", user=Depends(get_current_user)):
    stage_id, class_name = enforce_scope(user, stage_id, class_name)
    path = _tmp_path(".pdf")
    db.export_stats_pdf(path, stage_id=stage_id, stage_label=label[:100], class_name=class_name)
    return _file_response(path, "attendance_stats.pdf", "application/pdf")


@app.get("/api/export/lessons_pdf")
def export_lessons_pdf(stage_id: int, user=Depends(get_current_user)):
    stage_id, _ = enforce_scope(user, stage_id, None)
    stage = next((s for s in db.get_all_stages() if s["id"] == stage_id), None)
    if stage is None:
        raise HTTPException(status_code=404, detail="المرحلة غير موجودة")
    path = _tmp_path(".pdf")
    db.export_lessons_pdf(path, stage_id, stage["name"])
    return _file_response(path, "lessons_plan.pdf", "application/pdf")


# ---------------------- المستخدمون (أدمن فقط) ----------------------

@app.get("/api/users")
def list_users(user=Depends(require_admin)):
    result = []
    for u in db.get_all_users():
        d = dict(u)
        d.pop("password_hash", None)  # لا يجب إرسال التجزئة للعميل أبدًا
        result.append(d)
    return result


@app.get("/api/users/count_admins")
def count_admins_endpoint(user=Depends(require_admin)):
    return {"count": db.count_admins()}


@app.post("/api/users")
def create_user_endpoint(body: UserCreateBody, user=Depends(require_admin)):
    if body.role not in ("admin", "servant"):
        raise HTTPException(status_code=400, detail="صلاحية غير صالحة")
    if body.role == "servant" and body.stage_id is None:
        raise HTTPException(status_code=400, detail="اختر مرحلة للخادم")
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="كلمة المرور قصيرة جدًا (4 حروف على الأقل)")
    ok, msg = db.create_user(body.username.strip(), body.password, role=body.role,
                                stage_id=body.stage_id if body.role == "servant" else None,
                                class_name=body.class_name if body.role == "servant" else None)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    db.log_activity(user["username"], "إضافة مستخدم", body.username.strip())
    return {"ok": True}


def _find_user(user_id):
    target = next((u for u in db.get_all_users() if u["id"] == user_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    return target


@app.put("/api/users/{user_id}")
def update_user_endpoint(user_id: int, body: UserUpdateBody, user=Depends(require_admin)):
    target = _find_user(user_id)
    if target["role"] == "admin" and body.role != "admin" and db.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="لا يمكن تحويل آخر أدمن إلى خادم")
    db.update_user(user_id, body.role, body.stage_id, body.class_name)
    _drop_sessions_for(target["username"])
    db.log_activity(user["username"], "تعديل صلاحيات مستخدم", target["username"])
    return {"ok": True}


@app.post("/api/users/{user_id}/reset_password")
def reset_password_endpoint(user_id: int, body: PasswordResetBody, user=Depends(require_admin)):
    target = _find_user(user_id)
    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="كلمة المرور قصيرة جدًا (4 حروف على الأقل)")
    db.reset_user_password(user_id, body.new_password)
    _drop_sessions_for(target["username"])
    db.log_activity(user["username"], "إعادة تعيين كلمة مرور", target["username"])
    return {"ok": True}


@app.delete("/api/users/{user_id}")
def delete_user_endpoint(user_id: int, user=Depends(require_admin)):
    target = _find_user(user_id)
    if target["username"] == user["username"]:
        raise HTTPException(status_code=400, detail="لا يمكنك حذف حسابك الحالي")
    if target["role"] == "admin" and db.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="لا يمكن حذف آخر أدمن")
    db.delete_user(user_id)
    _drop_sessions_for(target["username"])
    db.log_activity(user["username"], "حذف مستخدم", target["username"])
    return {"ok": True}


# ---------------------- سجل النشاط (أدمن فقط) ----------------------

@app.get("/api/activity_log")
def activity_log(limit: int = 300, user=Depends(require_admin)):
    return [dict(a) for a in db.get_recent_activity(limit=min(limit, 1000))]


# ---------------------- النسخ الاحتياطي (أدمن فقط) ----------------------

@app.post("/api/backup")
def create_backup(user=Depends(require_admin)):
    path = db.backup_database()
    db.log_activity(user["username"], "نسخة احتياطية يدوية", os.path.basename(path))
    return {"name": os.path.basename(path)}


@app.get("/api/backups")
def list_backups(user=Depends(require_admin)):
    return [os.path.basename(p) for p in db.list_backups()]


@app.post("/api/backup/restore")
def restore_backup(body: RestoreBody, user=Depends(require_admin)):
    by_name = {os.path.basename(p): p for p in db.list_backups()}
    if body.name not in by_name:  # منع أي مسارات خارجية (Path Traversal)
        raise HTTPException(status_code=400, detail="النسخة الاحتياطية غير موجودة")
    db.restore_from_backup(by_name[body.name])
    SESSIONS.clear()  # البيانات اتغيّرت بالكامل، الكل لازم يسجّل دخول من جديد
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}


# ---------------------- تقديم ملفات الواجهة (PWA) ----------------------
# لازم تتسجل بعد كل مسارات /api عشان الأولوية تبقى للـ API أولًا

if os.path.isdir(os.path.join(WEBAPP_DIR, "icons")):
    app.mount("/icons", StaticFiles(directory=os.path.join(WEBAPP_DIR, "icons")), name="icons")


@app.get("/{full_path:path}")
def serve_webapp(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    index = os.path.join(WEBAPP_DIR, "index.html")
    if not os.path.isfile(index):
        raise HTTPException(status_code=404, detail="ملفات تطبيق الويب غير موجودة")
    requested = os.path.normpath(os.path.join(WEBAPP_DIR, full_path)) if full_path else index
    # منع الخروج من فولدر الويب (Path Traversal)
    if requested.startswith(os.path.normpath(WEBAPP_DIR)) and os.path.isfile(requested):
        return FileResponse(requested)
    return FileResponse(index)
