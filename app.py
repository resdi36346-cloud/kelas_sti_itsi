import os
import secrets
import uuid
import random
from datetime import date, datetime
from functools import wraps
from io import BytesIO

import pandas as pd
from flask import (
    Flask, abort, flash, redirect, render_template, request, send_file,
    url_for, session,
)
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from models import (
    db, User, KasBulanan, PeriodePenilaian, PenilaianSikap,
    PerangkatKelas, PenilaianKinerjaPerangkat, GroupSet, GroupMember,
)
from seed import seed_database


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "ganti-secret-key-portal-sti-itsi"),
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(BASE_DIR, 'kelas_sti.db')}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,
    UPLOAD_FOLDER=UPLOAD_FOLDER,
)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Silakan login untuk mengakses halaman tersebut."
login_manager.login_message_category = "warning"

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
KAS_STATUSES = ("Lunas", "Menyicil", "Belum Bayar")
ASPECTS = [
    ("kedisiplinan", "Kedisiplinan"),
    ("kerja_sama", "Kerja Sama Tim"),
    ("etika_komunikasi", "Etika & Komunikasi"),
    ("tanggung_jawab", "Tanggung Jawab"),
]
DEVICE_ASPECTS = [
    ("kedisiplinan", "Kedisiplinan"),
    ("tanggung_jawab", "Tanggung Jawab"),
    ("kepemimpinan", "Kepemimpinan"),
    ("komunikasi", "Komunikasi"),
    ("pelaksanaan_tugas", "Pelaksanaan Tugas"),
]
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def role_required(*roles):
    def decorator(view_function):
        @wraps(view_function)
        @login_required
        def wrapped_view(*args, **kwargs):
            if current_user.role not in roles:
                flash("Anda tidak memiliki izin untuk membuka halaman tersebut.", "danger")
                return redirect(url_for("index"))
            return view_function(*args, **kwargs)
        return wrapped_view
    return decorator


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        expected = session.get("_csrf_token")
        supplied = request.form.get("_csrf_token", "")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description="Token keamanan form tidak valid. Muat ulang halaman lalu coba lagi.")


@app.context_processor
def inject_template_helpers():
    def csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_urlsafe(32)
        return session["_csrf_token"]

    return {
        "csrf_token": csrf_token,
        "month_names": MONTH_NAMES,
        "kas_statuses": KAS_STATUSES,
        "current_year": date.today().year,
        "current_month": date.today().month,
        "DEVICE_ASPECTS": DEVICE_ASPECTS,
        "ASPECTS": ASPECTS,
    }


def parse_optional_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def get_upload_error(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        return "File foto harus memiliki ekstensi yang valid."
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return "Format foto harus PNG, JPG, JPEG, atau WEBP."
    return None


def save_profile_photo(file_storage, old_photo=None):
    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    destination = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
    file_storage.save(destination)
    if old_photo:
        old_path = os.path.join(app.config["UPLOAD_FOLDER"], os.path.basename(old_photo))
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                app.logger.warning("Tidak dapat menghapus foto lama: %s", old_path)
    return stored_name


def get_rating_summary(students, period_id=None):
    query = PenilaianSikap.query
    if period_id:
        query = query.filter_by(periode_id=period_id)
    all_ratings = query.all()
    by_student = {student.id: [] for student in students}
    for rating in all_ratings:
        if rating.dinilai_id in by_student:
            by_student[rating.dinilai_id].append(rating)
    summary = []
    for student in students:
        ratings = by_student[student.id]
        aspects = {}
        for field, _label in ASPECTS:
            values = [getattr(row, field) for row in ratings]
            aspects[field] = round(sum(values) / len(values), 2) if values else 0
        overall = round(sum(aspects.values()) / len(aspects), 2) if ratings else 0
        summary.append({"student": student, "count": len(ratings), "aspects": aspects, "overall": overall})
    summary.sort(key=lambda item: (item["overall"], item["count"], item["student"].name), reverse=True)
    return summary


def get_device_rating_summary(period_id=None):
    query = PenilaianKinerjaPerangkat.query
    if period_id:
        query = query.filter_by(periode_id=period_id)
    ratings = query.all()
    grouped = {}
    for rating in ratings:
        key = (
            rating.perangkat_id, rating.holder_id_snapshot, rating.jabatan_snapshot,
            rating.holder_name_snapshot, rating.holder_nim_snapshot, rating.holder_photo_snapshot,
        )
        grouped.setdefault(key, []).append(rating)
    summary = []
    for key, rows in grouped.items():
        device_id, holder_id, role_name, holder_name, holder_nim, holder_photo = key
        aspects = {}
        for field, _label in DEVICE_ASPECTS:
            values = [getattr(row, field) for row in rows]
            aspects[field] = round(sum(values) / len(values), 2) if values else 0
        summary.append({
            "device_id": device_id, "holder_id": holder_id, "jabatan": role_name,
            "holder_name": holder_name, "holder_nim": holder_nim or "—",
            "holder_photo": holder_photo, "count": len(rows), "aspects": aspects,
            "overall": round(sum(aspects.values()) / len(aspects), 2) if aspects else 0,
            "feedbacks": [row.catatan for row in rows if row.catatan and row.catatan.strip()],
        })
    summary.sort(key=lambda item: (item["overall"], item["count"], item["jabatan"].lower()), reverse=True)
    return summary


def get_personal_device_summary(user_id, period_id=None):
    query = PenilaianKinerjaPerangkat.query.filter_by(holder_id_snapshot=user_id)
    if period_id:
        query = query.filter_by(periode_id=period_id)
    ratings = query.order_by(PenilaianKinerjaPerangkat.created_at.desc()).all()
    grouped = {}
    for row in ratings:
        grouped.setdefault(row.jabatan_snapshot, []).append(row)
    result = []
    for jabatan, rows in grouped.items():
        scores = [row.average_score for row in rows]
        result.append({
            "jabatan": jabatan, "count": len(rows),
            "average": round(sum(scores) / len(scores), 2) if scores else 0,
            "feedbacks": [row.catatan for row in rows if row.catatan and row.catatan.strip()],
        })
    return sorted(result, key=lambda item: item["jabatan"])


def current_period():
    active = PeriodePenilaian.query.filter_by(is_active=True).first()
    if active:
        return active
    periods = PeriodePenilaian.query.order_by(PeriodePenilaian.created_at.desc()).all()
    return next((period for period in periods if "(Arsip" not in (period.name or "")), periods[0] if periods else None)


def public_period_data(students):
    periods = PeriodePenilaian.query.order_by(
        PeriodePenilaian.year.desc(), PeriodePenilaian.month.desc(),
        PeriodePenilaian.created_at.desc()
    ).all()
    period_id = request.args.get("ranking_period_id", type=int)
    selected = db.session.get(PeriodePenilaian, period_id) if period_id else None
    selected = selected or current_period()
    student_ranking = get_rating_summary(students, selected.id) if selected else []
    student_ranking = [item for item in student_ranking if item["count"]]
    device_ranking = get_device_rating_summary(selected.id) if selected else []
    return periods, selected, student_ranking, device_ranking


# -----------------------------------------------------------------------------
# HALAMAN PUBLIK
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    students = User.query.filter_by(role="mahasiswa", is_active=True).order_by(User.nim.asc()).all()
    periods, ranking_period, monthly_ranking, device_ranking = public_period_data(students)
    today = date.today()
    year = request.args.get("cash_year", type=int) or 2026
    cash_month = today.month
    cash_rows = KasBulanan.query.filter_by(year=year, month=cash_month).all()
    total_due = sum(row.amount_due for row in cash_rows)
    total_paid = sum(row.amount_paid for row in cash_rows)
    completion = round(total_paid / total_due * 100, 1) if total_due else 0
    active_devices = PerangkatKelas.query.filter_by(is_active=True).all()
    return render_template(
        "index.html", students=students, ranking_periods=periods,
        ranking_period=ranking_period, monthly_ranking=monthly_ranking,
        device_ranking=device_ranking, total_students=len(students),
        total_due=total_due, total_paid=total_paid, completion=completion,
        active_device_count=len(active_devices), today=today,
        particles_enabled=True,
    )


@app.route("/directory")
def directory():
    students = User.query.filter_by(role="mahasiswa", is_active=True).order_by(User.nim.asc()).all()
    return render_template("directory.html", students=students, particles_enabled=False)


@app.route("/directory/<int:user_id>")
def student_detail(user_id):
    student = User.query.filter_by(id=user_id, role="mahasiswa", is_active=True).first_or_404()
    return render_template("student_detail.html", student=student, particles_enabled=False)


@app.route("/kas")
def public_cash():
    students = User.query.filter_by(role="mahasiswa", is_active=True).order_by(User.nim.asc()).all()
    year = request.args.get("year", type=int) or 2026
    rows = KasBulanan.query.filter_by(year=year).all()
    cash_map = {(row.user_id, row.month): row for row in rows}
    monthly_summary = []
    for month in range(1, 13):
        month_rows = [cash_map.get((student.id, month)) for student in students]
        present = [row for row in month_rows if row]
        monthly_summary.append({
            "month": month,
            "total_paid": sum(row.amount_paid for row in present),
            "total_due": sum(row.amount_due for row in present),
            "settled": sum(1 for row in present if row.status == "Lunas"),
            "recorded": len(present),
        })
    return render_template(
        "public_cash.html", students=students, cash_map=cash_map,
        monthly_summary=monthly_summary, selected_year=year,
        particles_enabled=False,
    )


@app.route("/kelompok")
def public_groups():
    """Halaman publik untuk melihat pembagian kelompok mata kuliah."""
    group_sets = GroupSet.query.order_by(GroupSet.created_at.desc()).all()
    return render_template("public_groups.html", group_sets=group_sets, particles_enabled=False)


# -----------------------------------------------------------------------------
# AUTENTIKASI
# -----------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.role == "admin" else "member_dashboard"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(or_(User.username == identity, User.nim == identity)).first()
        if user and user.is_active and user.check_password(password):
            login_user(user)
            flash(f"Selamat datang, {user.name}.", "success")
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("admin_dashboard" if user.role == "admin" else "member_dashboard"))
        flash("NIM/username atau password tidak sesuai.", "danger")
    return render_template("login.html", particles_enabled=True)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Anda berhasil keluar dari portal.", "info")
    return redirect(url_for("index"))


# -----------------------------------------------------------------------------
# AREA MAHASISWA - SETIAP FITUR DALAM HALAMAN TERPISAH
# -----------------------------------------------------------------------------
def member_common_context():
    students = User.query.filter_by(role="mahasiswa", is_active=True).order_by(User.name.asc()).all()
    period = current_period()
    peers = [student for student in students if student.id != current_user.id]
    evaluated_ids = set()
    if period:
        evaluated_ids = {
            row.dinilai_id for row in PenilaianSikap.query.filter_by(
                periode_id=period.id, penilai_id=current_user.id
            ).all()
        }
    devices = PerangkatKelas.query.filter_by(is_active=True).order_by(PerangkatKelas.jabatan.asc()).all()
    devices = [d for d in devices if d.holder and d.holder.is_active]
    assessable_devices = [d for d in devices if d.holder_id != current_user.id]
    evaluated_device_ids = set()
    if period:
        evaluated_device_ids = {
            row.perangkat_id for row in PenilaianKinerjaPerangkat.query.filter_by(
                periode_id=period.id, penilai_id=current_user.id
            ).all()
        }
    return {
        "students": students, "period": period, "peers": peers,
        "evaluated_ids": evaluated_ids, "progress": len(evaluated_ids),
        "peer_total": len(peers), "devices": devices,
        "assessable_devices": assessable_devices,
        "evaluated_device_ids": evaluated_device_ids,
        "device_progress": len(evaluated_device_ids.intersection({d.id for d in assessable_devices})),
        "device_total": len(assessable_devices),
    }


@app.route("/member/dashboard")
@role_required("mahasiswa")
def member_dashboard():
    context = member_common_context()
    return render_template("member_dashboard.html", **context, particles_enabled=True)


@app.route("/member/assessment")
@role_required("mahasiswa")
def member_assessment():
    context = member_common_context()
    return render_template("member_assessment.html", **context, particles_enabled=False)


@app.route("/member/devices")
@role_required("mahasiswa")
def member_devices():
    context = member_common_context()
    return render_template("member_devices.html", **context, particles_enabled=False)


@app.route("/member/report")
@role_required("mahasiswa")
def member_report():
    context = member_common_context()
    period = context["period"]
    received_query = PenilaianSikap.query.filter_by(dinilai_id=current_user.id)
    if period:
        received_query = received_query.filter_by(periode_id=period.id)
    received = received_query.order_by(PenilaianSikap.created_at.desc()).all()
    aspect_scores = {}
    for field, label in ASPECTS:
        values = [getattr(row, field) for row in received]
        aspect_scores[label] = round(sum(values) / len(values), 2) if values else 0
    feedbacks = [row.catatan for row in received if row.catatan and row.catatan.strip()]
    device_summary = get_personal_device_summary(current_user.id, period.id if period else None)
    return render_template(
        "member_report.html", **context, aspect_scores=aspect_scores,
        feedbacks=feedbacks, device_self_summary=device_summary,
        device_self_feedbacks=[note for item in device_summary for note in item["feedbacks"]],
        particles_enabled=False,
    )


@app.route("/member/groups")
@role_required("mahasiswa")
def member_groups():
    group_sets = GroupSet.query.order_by(GroupSet.created_at.desc()).all()
    return render_template("member_groups.html", group_sets=group_sets, particles_enabled=False)


@app.route("/member/profile", methods=["GET", "POST"])
@role_required("mahasiswa")
def member_profile():
    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if new_password:
            if len(new_password) < 6 or new_password != confirm_password or not current_user.check_password(old_password):
                flash("Periksa password lama, panjang password baru (minimal 6), dan konfirmasinya.", "danger")
                return redirect(url_for("member_profile"))
        photo = request.files.get("photo")
        photo_error = get_upload_error(photo)
        if photo_error:
            flash(photo_error, "danger")
            return redirect(url_for("member_profile"))
        # Mahasiswa tidak dapat mengubah biodata inti. Hanya akun/foto dan bio non-biodata.
        current_user.motto = request.form.get("motto", "").strip()[:255]
        current_user.hobbies = request.form.get("hobbies", "").strip()[:255]
        current_user.instagram = request.form.get("instagram", "").strip()[:120]
        current_user.linkedin = request.form.get("linkedin", "").strip()[:180]
        current_user.tiktok = request.form.get("tiktok", "").strip()[:120]
        if photo and photo.filename:
            current_user.photo = save_profile_photo(photo, current_user.photo)
        if new_password:
            current_user.set_password(new_password)
        db.session.commit()
        flash("Pengaturan profil berhasil disimpan.", "success")
        return redirect(url_for("member_profile"))
    return render_template("member_profile.html", particles_enabled=False)


@app.route("/member/evaluate/<int:target_id>", methods=["POST"])
@role_required("mahasiswa")
def submit_evaluation(target_id):
    period = PeriodePenilaian.query.filter_by(is_active=True).first()
    target = User.query.filter_by(id=target_id, role="mahasiswa", is_active=True).first_or_404()
    if target.id == current_user.id:
        flash("Anda tidak dapat menilai diri sendiri.", "danger")
        return redirect(url_for("member_assessment"))
    if period is None:
        flash("Belum ada periode penilaian yang aktif.", "warning")
        return redirect(url_for("member_assessment"))
    if PenilaianSikap.query.filter_by(periode_id=period.id, penilai_id=current_user.id, dinilai_id=target.id).first():
        flash("Anda sudah menilai mahasiswa tersebut pada periode ini.", "warning")
        return redirect(url_for("member_assessment"))
    try:
        scores = {field: int(request.form.get(field, "")) for field, _label in ASPECTS}
    except (TypeError, ValueError):
        flash("Pilih skor 1 sampai 5 untuk semua aspek.", "danger")
        return redirect(url_for("member_assessment"))
    if any(value < 1 or value > 5 for value in scores.values()):
        flash("Skor harus berada pada rentang 1–5.", "danger")
        return redirect(url_for("member_assessment"))
    rating = PenilaianSikap(
        periode_id=period.id, penilai_id=current_user.id, dinilai_id=target.id,
        **scores, catatan=request.form.get("catatan", "").strip()[:500] or None,
    )
    db.session.add(rating)
    try:
        db.session.commit()
        flash("Penilaian sikap berhasil disimpan secara anonim.", "success")
    except Exception:
        db.session.rollback()
        flash("Penilaian tidak dapat disimpan; mungkin Anda sudah menilai teman tersebut.", "danger")
    return redirect(url_for("member_assessment"))


@app.route("/member/device-evaluate/<int:device_id>", methods=["POST"])
@role_required("mahasiswa")
def submit_device_evaluation(device_id):
    period = PeriodePenilaian.query.filter_by(is_active=True).first()
    device = PerangkatKelas.query.filter_by(id=device_id, is_active=True).first_or_404()
    holder = device.holder
    if period is None:
        flash("Belum ada periode penilaian yang aktif.", "warning")
        return redirect(url_for("member_devices"))
    if not holder or not holder.is_active:
        flash("Pemegang jabatan belum ditentukan admin.", "warning")
        return redirect(url_for("member_devices"))
    if holder.id == current_user.id:
        flash("Anda tidak dapat menilai jabatan yang sedang Anda pegang sendiri.", "danger")
        return redirect(url_for("member_devices"))
    existing = PenilaianKinerjaPerangkat.query.filter_by(
        periode_id=period.id, penilai_id=current_user.id, perangkat_id=device.id
    ).first()
    if existing:
        flash("Anda sudah menilai jabatan ini pada periode berjalan.", "warning")
        return redirect(url_for("member_devices"))
    try:
        scores = {field: int(request.form.get(field, "")) for field, _label in DEVICE_ASPECTS}
    except (TypeError, ValueError):
        flash("Pilih skor 1 sampai 5 untuk seluruh aspek kinerja.", "danger")
        return redirect(url_for("member_devices"))
    if any(value < 1 or value > 5 for value in scores.values()):
        flash("Skor kinerja harus berada pada rentang 1–5.", "danger")
        return redirect(url_for("member_devices"))
    rating = PenilaianKinerjaPerangkat(
        periode_id=period.id, perangkat_id=device.id, penilai_id=current_user.id,
        holder_id_snapshot=holder.id, jabatan_snapshot=device.jabatan,
        holder_name_snapshot=holder.name, holder_nim_snapshot=holder.nim,
        holder_photo_snapshot=holder.photo, **scores,
        catatan=request.form.get("catatan", "").strip()[:500] or None,
    )
    db.session.add(rating)
    try:
        db.session.commit()
        flash("Penilaian kinerja perangkat kelas berhasil dikirim secara anonim.", "success")
    except Exception:
        db.session.rollback()
        flash("Penilaian tidak dapat disimpan. Periksa apakah Anda sudah menilai jabatan tersebut.", "danger")
    return redirect(url_for("member_devices"))


# -----------------------------------------------------------------------------
# AREA ADMIN - RINGKASAN + SATU HALAMAN UNTUK SETIAP KATEGORI
# -----------------------------------------------------------------------------
def admin_students():
    return User.query.filter_by(role="mahasiswa").order_by(User.nim.asc()).all()


@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    students = admin_students()
    active_period = PeriodePenilaian.query.filter_by(is_active=True).first()
    periods_count = PeriodePenilaian.query.count()
    ratings_count = PenilaianSikap.query.count()
    devices_count = PerangkatKelas.query.filter_by(is_active=True).count()
    devices_ratings_count = PenilaianKinerjaPerangkat.query.count()
    current_month = date.today().month
    current_year = date.today().year
    kas_count = KasBulanan.query.filter_by(year=current_year, month=current_month).count()
    groups_count = GroupSet.query.count()
    return render_template(
        "admin_dashboard.html", students=students, active_period=active_period,
        periods_count=periods_count, ratings_count=ratings_count,
        devices_count=devices_count, devices_ratings_count=devices_ratings_count,
        kas_count=kas_count, groups_count=groups_count, particles_enabled=True,
    )


@app.route("/admin/periods", methods=["GET", "POST"])
@role_required("admin")
def admin_periods():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:120]
        month = request.form.get("month", type=int)
        year = request.form.get("year", type=int)
        activate = request.form.get("activate") == "on"
        if not month or not 1 <= month <= 12 or not year or year < 2020 or year > 2100:
            flash("Pilih bulan dan tahun periode dengan benar.", "danger")
            return redirect(url_for("admin_periods"))

        # Satu periode kalender per bulan: penilaian sikap dan perangkat
        # menggunakan periode bulanan yang sama.
        existing = PeriodePenilaian.query.filter_by(year=year, month=month).order_by(
            PeriodePenilaian.created_at.desc()
        ).first()
        if existing:
            flash(
                f"Periode {MONTH_NAMES[month - 1]} {year} sudah tersedia. "
                "Aktifkan periode yang ada; setiap mahasiswa hanya menilai sekali dalam bulan tersebut.",
                "warning",
            )
            return redirect(url_for("admin_periods"))

        if not name:
            name = f"{MONTH_NAMES[month - 1]} {year}"
        if activate:
            PeriodePenilaian.query.update({"is_active": False, "closed_at": datetime.utcnow()})
        db.session.add(PeriodePenilaian(
            name=name,
            # Kept at 1 for compatibility with older SQLite databases. The UI
            # and validation now treat the period as one complete month.
            week_number=1,
            month=month,
            year=year,
            is_active=activate,
            closed_at=None if activate else datetime.utcnow(),
        ))
        db.session.commit()
        flash(f"Periode bulanan {name} berhasil dibuat.", "success")
        return redirect(url_for("admin_periods"))

    periods = PeriodePenilaian.query.order_by(
        PeriodePenilaian.year.desc(), PeriodePenilaian.month.desc(),
        PeriodePenilaian.created_at.desc()
    ).all()
    # Database lama mungkin berisi beberapa sesi mingguan dalam bulan yang sama.
    # Periode aktif diprioritaskan; jika tidak ada, gunakan periode terbaru.
    primary_period_ids = set()
    grouped_periods = {}
    for item in periods:
        grouped_periods.setdefault((item.year, item.month), []).append(item)
    for same_month in grouped_periods.values():
        active_item = next((item for item in same_month if item.is_active), None)
        named_primary = next((item for item in same_month if "(Arsip" not in (item.name or "")), None)
        primary_period_ids.add((active_item or named_primary or same_month[0]).id)
    progress = {}
    students = admin_students()
    for period in periods:
        counts = dict(
            db.session.query(PenilaianSikap.penilai_id, func.count(PenilaianSikap.id))
            .filter(PenilaianSikap.periode_id == period.id)
            .group_by(PenilaianSikap.penilai_id).all()
        )
        progress[period.id] = [
            {"student": student, "count": min(counts.get(student.id, 0), max(len(students) - 1, 0)),
             "total": max(len(students) - 1, 0)}
            for student in students
        ]
    return render_template(
        "admin_periods.html", periods=periods, progress=progress,
        primary_period_ids=primary_period_ids, particles_enabled=False,
    )

@app.route("/admin/periods/<int:period_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_period(period_id):
    period = PeriodePenilaian.query.get_or_404(period_id)
    if period.is_active:
        period.is_active = False
        period.closed_at = datetime.utcnow()
        message = "Periode penilaian ditutup."
    else:
        same_month_periods = PeriodePenilaian.query.filter_by(
            year=period.year, month=period.month
        ).order_by(PeriodePenilaian.created_at.desc(), PeriodePenilaian.id.desc()).all()
        active_same_month = next((item for item in same_month_periods if item.is_active), None)
        named_primary = next((item for item in same_month_periods if "(Arsip" not in (item.name or "")), None)
        primary_period = active_same_month or named_primary or (same_month_periods[0] if same_month_periods else period)
        if primary_period.id != period.id:
            flash(
                "Periode ini merupakan arsip periode lama. Untuk menjaga aturan satu kali per bulan, "
                "hanya periode utama bulan tersebut yang dapat diaktifkan.",
                "warning",
            )
            return redirect(url_for("admin_periods"))
        PeriodePenilaian.query.update({"is_active": False, "closed_at": datetime.utcnow()})
        period.is_active = True
        period.closed_at = None
        message = "Periode bulanan diaktifkan."
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("admin_periods"))


@app.route("/admin/rekap")
@role_required("admin")
def admin_recap():
    students = admin_students()
    periods = PeriodePenilaian.query.order_by(PeriodePenilaian.year.desc(), PeriodePenilaian.month.desc(), PeriodePenilaian.created_at.desc()).all()
    period_id = request.args.get("period_id", type=int)
    selected = db.session.get(PeriodePenilaian, period_id) if period_id else current_period()
    selected_id = selected.id if selected else None
    student_summary = get_rating_summary(students, selected_id)
    device_summary = get_device_rating_summary(selected_id)
    return render_template(
        "admin_recap.html", periods=periods, selected_period=selected,
        student_summary=student_summary, device_summary=device_summary,
        particles_enabled=False,
    )


@app.route("/admin/perangkat", methods=["GET", "POST"])
@role_required("admin")
def admin_devices():
    if request.method == "POST":
        jabatan = request.form.get("jabatan", "").strip()[:100]
        holder_id = request.form.get("holder_id", type=int)
        deskripsi = request.form.get("deskripsi", "").strip()[:255]
        holder = User.query.filter_by(id=holder_id, role="mahasiswa", is_active=True).first() if holder_id else None
        if not jabatan or not holder:
            flash("Nama jabatan dan pemegang wajib dipilih.", "danger")
        else:
            db.session.add(PerangkatKelas(jabatan=jabatan, holder_id=holder.id, deskripsi=deskripsi or None, is_active=True))
            db.session.commit()
            flash(f"Jabatan {jabatan} berhasil ditambahkan.", "success")
        return redirect(url_for("admin_devices"))
    students = admin_students()
    devices = PerangkatKelas.query.order_by(PerangkatKelas.is_active.desc(), PerangkatKelas.jabatan.asc()).all()
    period_id = request.args.get("period_id", type=int)
    selected_period = db.session.get(PeriodePenilaian, period_id) if period_id else current_period()
    selected_id = selected_period.id if selected_period else None
    ratings_query = PenilaianKinerjaPerangkat.query
    if selected_id:
        ratings_query = ratings_query.filter_by(periode_id=selected_id)
    device_ratings = ratings_query.order_by(PenilaianKinerjaPerangkat.jabatan_snapshot.asc(), PenilaianKinerjaPerangkat.created_at.desc()).all()
    device_summary = get_device_rating_summary(selected_id)
    periods = PeriodePenilaian.query.order_by(PeriodePenilaian.year.desc(), PeriodePenilaian.month.desc(), PeriodePenilaian.created_at.desc()).all()
    return render_template(
        "admin_devices.html", students=students, devices=devices,
        device_ratings=device_ratings, device_summary=device_summary,
        periods=periods, selected_period=selected_period,
        expected_raters=max(len(students)-1, 0), particles_enabled=False,
    )


@app.route("/admin/devices/<int:device_id>/edit", methods=["POST"])
@role_required("admin")
def edit_device(device_id):
    device = PerangkatKelas.query.get_or_404(device_id)
    jabatan = request.form.get("jabatan", "").strip()[:100]
    holder_id = request.form.get("holder_id", type=int)
    deskripsi = request.form.get("deskripsi", "").strip()[:255]
    holder = User.query.filter_by(id=holder_id, role="mahasiswa", is_active=True).first() if holder_id else None
    if not jabatan or not holder:
        flash("Jabatan dan pemegang harus valid.", "danger")
    else:
        device.jabatan, device.holder_id, device.deskripsi = jabatan, holder.id, deskripsi or None
        db.session.commit()
        flash("Perangkat kelas berhasil diperbarui. Riwayat lama tetap tersimpan.", "success")
    return redirect(url_for("admin_devices"))


@app.route("/admin/devices/<int:device_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_device(device_id):
    device = PerangkatKelas.query.get_or_404(device_id)
    device.is_active = not device.is_active
    db.session.commit()
    flash(f"{device.jabatan} {'diaktifkan' if device.is_active else 'dinonaktifkan'}.", "success")
    return redirect(url_for("admin_devices"))


@app.route("/admin/devices/<int:device_id>/delete", methods=["POST"])
@role_required("admin")
def delete_device(device_id):
    device = PerangkatKelas.query.get_or_404(device_id)
    if PenilaianKinerjaPerangkat.query.filter_by(perangkat_id=device.id).first():
        device.is_active = False
        flash("Jabatan memiliki riwayat; jabatan dinonaktifkan agar histori terjaga.", "info")
    else:
        db.session.delete(device)
        flash("Jabatan dihapus.", "success")
    db.session.commit()
    return redirect(url_for("admin_devices"))


@app.route("/admin/kas")
@role_required("admin")
def admin_cash():
    students = admin_students()
    year = request.args.get("year", type=int) or 2026
    month = request.args.get("month", type=int) or date.today().month
    if not 1 <= month <= 12:
        month = date.today().month
    rows = KasBulanan.query.filter_by(year=year, month=month).all()
    kas_map = {row.user_id: row for row in rows}
    amount_due = rows[0].amount_due if rows else 20000
    return render_template(
        "admin_cash.html", students=students, kas_map=kas_map,
        selected_year=year, selected_month=month, amount_due=amount_due,
        recorded_count=len(rows), particles_enabled=False,
    )


@app.route("/admin/kas/bulk-update", methods=["POST"])
@role_required("admin")
def bulk_update_cash():
    year = request.form.get("year", type=int)
    month = request.form.get("month", type=int)
    amount_due = request.form.get("amount_due", type=int)
    if not year or not month or not 1 <= month <= 12 or amount_due is None or amount_due < 0:
        flash("Tahun, bulan, atau nominal iuran tidak valid.", "danger")
        return redirect(url_for("admin_cash"))
    students = admin_students()
    for student in students:
        status = request.form.get(f"status_{student.id}", "Kosong")
        paid_raw = request.form.get(f"paid_{student.id}", "0")
        try:
            paid = max(0, int(paid_raw or 0))
        except ValueError:
            paid = 0
        row = KasBulanan.query.filter_by(user_id=student.id, year=year, month=month).first()
        if status == "Kosong":
            if row:
                db.session.delete(row)
            continue
        if status not in KAS_STATUSES:
            status = "Belum Bayar"
        if row is None:
            row = KasBulanan(user_id=student.id, year=year, month=month, amount_due=amount_due, amount_paid=0, status="Belum Bayar")
            db.session.add(row)
        row.amount_due = amount_due
        if status == "Lunas":
            row.amount_paid = amount_due
        elif status == "Belum Bayar":
            row.amount_paid = 0
        else:
            row.amount_paid = min(paid, amount_due)
            if row.amount_paid <= 0:
                row.amount_paid = 0
                row.status = "Belum Bayar"
                continue
            if amount_due and row.amount_paid >= amount_due:
                row.status = "Lunas"
                row.amount_paid = amount_due
                continue
        row.status = status
    db.session.commit()
    flash("Seluruh perubahan kas berhasil disimpan sekaligus.", "success")
    return redirect(url_for("admin_cash", year=year, month=month))


@app.route("/admin/mahasiswa", methods=["GET", "POST"])
@role_required("admin")
def admin_students_page():
    if request.method == "POST":
        students = admin_students()
        # Validasi NIM unik terlebih dahulu agar penyimpanan massal atomik.
        proposed = []
        for student in students:
            nim = request.form.get(f"nim_{student.id}", "").strip()
            name = request.form.get(f"name_{student.id}", "").strip()
            if not nim or not name:
                flash(f"Nama dan NIM wajib diisi untuk {student.name}.", "danger")
                return redirect(url_for("admin_students_page"))
            proposed.append((student, nim, name))
        nims = [item[1] for item in proposed]
        if len(nims) != len(set(nims)):
            flash("Ada NIM duplikat pada perubahan. Periksa kembali sebelum menyimpan.", "danger")
            return redirect(url_for("admin_students_page"))
        existing = User.query.filter(User.role == "mahasiswa", User.nim.in_(nims)).all()
        allowed_ids = {student.id for student, _nim, _name in proposed}
        if any(row.id not in allowed_ids for row in existing):
            flash("Salah satu NIM sudah digunakan akun lain.", "danger")
            return redirect(url_for("admin_students_page"))
        # Kosongkan sementara nilai unik supaya admin boleh menukar NIM antar mahasiswa sekaligus.
        for student, _nim, _name in proposed:
            temporary = f"__sti_tmp_{student.id}_{uuid.uuid4().hex[:8]}"
            student.nim = temporary
            student.username = temporary
        db.session.flush()
        for student, nim, name in proposed:
            student.nim = nim
            student.username = f"m{nim}"
            student.name = name[:120]
            student.gender = request.form.get(f"gender_{student.id}", "").strip() or None
            student.position = request.form.get(f"position_{student.id}", "Anggota").strip()[:80] or "Anggota"
            student.origin = request.form.get(f"origin_{student.id}", "").strip()[:120] or None
            student.birth_date = parse_optional_date(request.form.get(f"birth_{student.id}", ""))
        db.session.commit()
        flash("Seluruh biodata inti mahasiswa berhasil disimpan sekaligus.", "success")
        return redirect(url_for("admin_students_page"))
    students = admin_students()
    return render_template("admin_students.html", students=students, particles_enabled=False)


@app.route("/admin/users/add", methods=["POST"])
@role_required("admin")
def add_student():
    nim = request.form.get("nim", "").strip()
    name = request.form.get("name", "").strip()
    if not nim or not name or User.query.filter(or_(User.nim == nim, User.username == f"m{nim}")).first():
        flash("Nama wajib diisi dan NIM harus unik.", "danger")
        return redirect(url_for("admin_students_page"))
    student = User(username=f"m{nim}", nim=nim, name=name[:120], role="mahasiswa")
    student.gender = request.form.get("gender", "").strip() or None
    student.position = request.form.get("position", "Anggota").strip()[:80] or "Anggota"
    student.origin = request.form.get("origin", "").strip()[:120] or None
    student.birth_date = parse_optional_date(request.form.get("birth_date", ""))
    student.set_password("123456")
    db.session.add(student)
    db.session.commit()
    flash(f"{name} ditambahkan. Password awal 123456.", "success")
    return redirect(url_for("admin_students_page"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def delete_student(user_id):
    student = User.query.filter_by(id=user_id, role="mahasiswa").first_or_404()
    PenilaianSikap.query.filter(or_(PenilaianSikap.penilai_id == student.id, PenilaianSikap.dinilai_id == student.id)).delete(synchronize_session=False)
    PenilaianKinerjaPerangkat.query.filter_by(penilai_id=student.id).delete(synchronize_session=False)
    PenilaianKinerjaPerangkat.query.filter_by(holder_id_snapshot=student.id).update({"holder_id_snapshot": None}, synchronize_session=False)
    PerangkatKelas.query.filter_by(holder_id=student.id).update({"holder_id": None}, synchronize_session=False)
    GroupMember.query.filter_by(user_id=student.id).delete(synchronize_session=False)
    db.session.delete(student)
    db.session.commit()
    flash("Mahasiswa dan relasi aktifnya berhasil dihapus.", "info")
    return redirect(url_for("admin_students_page"))


@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@role_required("admin")
def reset_student_password(user_id):
    student = User.query.filter_by(id=user_id, role="mahasiswa").first_or_404()
    student.set_password("123456")
    db.session.commit()
    flash(f"Password {student.name} direset menjadi 123456.", "success")
    return redirect(url_for("admin_students_page"))


@app.route("/admin/akun", methods=["GET", "POST"])
@role_required("admin")
def admin_account():
    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not current_user.check_password(old_password):
            flash("Password lama tidak sesuai.", "danger")
        elif len(new_password) < 8:
            flash("Password baru minimal 8 karakter.", "danger")
        elif new_password != confirm:
            flash("Konfirmasi password tidak sama.", "danger")
        elif new_password == old_password:
            flash("Password baru harus berbeda dari password lama.", "warning")
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash("Password admin berhasil diganti.", "success")
        return redirect(url_for("admin_account"))
    return render_template("admin_account.html", particles_enabled=False)


def resequence_group_members(group_set_id, group_numbers):
    """Rapikan nomor urut anggota setelah dipindah atau dikeluarkan."""
    for group_number in set(group_numbers):
        members = GroupMember.query.filter_by(
            group_set_id=group_set_id, group_number=group_number
        ).order_by(GroupMember.position.asc(), GroupMember.id.asc()).all()
        for position, member in enumerate(members, start=1):
            member.position = position


@app.route("/admin/kelompok", methods=["GET", "POST"])
@role_required("admin")
def admin_groups():
    if request.method == "POST":
        course = request.form.get("course", "").strip()[:120]
        topic = request.form.get("topic", "").strip()[:180]
        group_count = request.form.get("group_count", type=int)
        members_per_group = request.form.get("members_per_group", type=int)
        students = User.query.filter_by(role="mahasiswa", is_active=True).order_by(User.nim.asc()).all()
        if not course or not group_count or group_count < 1 or not members_per_group or members_per_group < 1:
            flash("Mata kuliah, jumlah kelompok, dan jumlah anggota harus diisi benar.", "danger")
            return redirect(url_for("admin_groups"))
        minimum_size = (len(students) + group_count - 1) // group_count
        if members_per_group < minimum_size:
            flash(
                f"Kapasitas belum cukup. Untuk {len(students)} mahasiswa dan {group_count} kelompok, "
                f"minimal {minimum_size} anggota per kelompok.", "danger"
            )
            return redirect(url_for("admin_groups"))

        random.SystemRandom().shuffle(students)
        group_set = GroupSet(
            course=course, topic=topic or None, group_count=group_count,
            members_per_group=members_per_group, created_by=current_user.id,
        )
        db.session.add(group_set)
        db.session.flush()
        group_buckets = [[] for _ in range(group_count)]
        for index, student in enumerate(students):
            group_buckets[index % group_count].append(student)
        for group_number, bucket in enumerate(group_buckets, start=1):
            for position, student in enumerate(bucket, start=1):
                db.session.add(GroupMember(
                    group_set_id=group_set.id, user_id=student.id,
                    group_number=group_number, position=position,
                ))
        db.session.commit()
        flash(f"Kelompok untuk {course} berhasil diacak. Anda masih bisa menambah atau memindahkan anggota secara manual.", "success")
        return redirect(url_for("admin_groups"))

    group_sets = GroupSet.query.order_by(GroupSet.created_at.desc()).all()
    students = User.query.filter_by(role="mahasiswa", is_active=True).order_by(User.nim.asc()).all()
    return render_template(
        "admin_groups.html", group_sets=group_sets, students=students,
        student_count=len(students), particles_enabled=False,
    )


@app.route("/admin/kelompok/<int:group_set_id>/assign", methods=["POST"])
@role_required("admin")
def assign_group_member(group_set_id):
    group_set = GroupSet.query.get_or_404(group_set_id)
    student_id = request.form.get("user_id", type=int)
    group_number = request.form.get("group_number", type=int)
    student = User.query.filter_by(id=student_id, role="mahasiswa", is_active=True).first() if student_id else None
    if not student or not group_number or not 1 <= group_number <= group_set.group_count:
        flash("Pilih mahasiswa dan nomor kelompok yang valid.", "danger")
        return redirect(url_for("admin_groups"))

    existing = GroupMember.query.filter_by(group_set_id=group_set.id, user_id=student.id).first()
    if existing and existing.group_number == group_number:
        flash(f"{student.name} sudah berada di Kelompok {group_number}.", "info")
        return redirect(url_for("admin_groups"))

    target_members = GroupMember.query.filter_by(
        group_set_id=group_set.id, group_number=group_number
    )
    target_count = target_members.count()
    if target_count >= group_set.members_per_group:
        flash(f"Kelompok {group_number} sudah mencapai kapasitas {group_set.members_per_group} orang.", "warning")
        return redirect(url_for("admin_groups"))

    next_position = (db.session.query(func.max(GroupMember.position)).filter_by(
        group_set_id=group_set.id, group_number=group_number
    ).scalar() or 0) + 1
    if existing:
        previous_group = existing.group_number
        existing.group_number = group_number
        existing.position = next_position
        resequence_group_members(group_set.id, [previous_group, group_number])
        message = f"{student.name} dipindahkan dari Kelompok {previous_group} ke Kelompok {group_number}."
    else:
        db.session.add(GroupMember(
            group_set_id=group_set.id, user_id=student.id,
            group_number=group_number, position=next_position,
        ))
        db.session.flush()
        resequence_group_members(group_set.id, [group_number])
        message = f"{student.name} ditambahkan ke Kelompok {group_number}."
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("admin_groups"))


@app.route("/admin/kelompok/<int:group_set_id>/member/<int:member_id>/remove", methods=["POST"])
@role_required("admin")
def remove_group_member(group_set_id, member_id):
    member = GroupMember.query.filter_by(group_set_id=group_set_id, id=member_id).first_or_404()
    name = member.student.name if member.student else "Anggota"
    group_number = member.group_number
    db.session.delete(member)
    db.session.flush()
    resequence_group_members(group_set_id, [group_number])
    db.session.commit()
    flash(f"{name} dikeluarkan dari pembagian kelompok ini.", "info")
    return redirect(url_for("admin_groups"))

@app.route("/admin/kelompok/<int:group_set_id>/delete", methods=["POST"])
@role_required("admin")
def delete_group_set(group_set_id):
    group_set = GroupSet.query.get_or_404(group_set_id)
    db.session.delete(group_set)
    db.session.commit()
    flash("Hasil pembagian kelompok dihapus.", "info")
    return redirect(url_for("admin_groups"))


@app.route("/admin/export.xlsx")
@role_required("admin")
def export_ratings():
    students = admin_students()
    period_id = request.args.get("period_id", type=int)
    period = db.session.get(PeriodePenilaian, period_id) if period_id else current_period()
    student_summary = get_rating_summary(students, period.id if period else None)
    student_data = []
    for rank, item in enumerate(student_summary, start=1):
        student_data.append({
            "Peringkat": rank, "NIM": item["student"].nim,
            "Nama": item["student"].name, "Penilaian Diterima": item["count"],
            "Kedisiplinan": item["aspects"]["kedisiplinan"],
            "Kerja Sama": item["aspects"]["kerja_sama"],
            "Etika & Komunikasi": item["aspects"]["etika_komunikasi"],
            "Tanggung Jawab": item["aspects"]["tanggung_jawab"],
            "Rata-rata": item["overall"],
        })
    student_details = []
    ratings = PenilaianSikap.query.filter_by(periode_id=period.id).all() if period else PenilaianSikap.query.all()
    for row in ratings:
        student_details.append({
            "Periode": row.periode.name if row.periode else "-",
            "NIM Dinilai": row.dinilai.nim if row.dinilai else "-",
            "Nama Dinilai": row.dinilai.name if row.dinilai else "-",
            "Kedisiplinan": row.kedisiplinan, "Kerja Sama": row.kerja_sama,
            "Etika & Komunikasi": row.etika_komunikasi, "Tanggung Jawab": row.tanggung_jawab,
            "Catatan Anonim": row.catatan or "",
        })
    device_summary = get_device_rating_summary(period.id if period else None)
    device_data = []
    for rank, item in enumerate(device_summary, start=1):
        device_data.append({
            "Peringkat": rank, "Jabatan": item["jabatan"], "Pemegang": item["holder_name"],
            "NIM": item["holder_nim"], "Jumlah Penilai": item["count"],
            **{label: item["aspects"][field] for field, label in DEVICE_ASPECTS},
            "Rata-rata": item["overall"],
            "Kesan dan Saran": " | ".join(item["feedbacks"]),
        })
    device_details = []
    device_query = PenilaianKinerjaPerangkat.query.filter_by(periode_id=period.id) if period else PenilaianKinerjaPerangkat.query
    for row in device_query.order_by(PenilaianKinerjaPerangkat.created_at.asc()).all():
        device_details.append({
            "Periode": row.periode.name if row.periode else "-",
            "Jabatan": row.jabatan_snapshot, "Pemegang": row.holder_name_snapshot,
            "Kedisiplinan": row.kedisiplinan, "Tanggung Jawab": row.tanggung_jawab,
            "Kepemimpinan": row.kepemimpinan, "Komunikasi": row.komunikasi,
            "Pelaksanaan Tugas": row.pelaksanaan_tugas, "Rata-rata": row.average_score,
            "Kesan dan Saran Anonim": row.catatan or "",
        })
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(student_data).to_excel(writer, sheet_name="Rekap Sikap", index=False)
        pd.DataFrame(student_details).to_excel(writer, sheet_name="Detail Sikap", index=False)
        pd.DataFrame(device_data).to_excel(writer, sheet_name="Rekap Perangkat", index=False)
        pd.DataFrame(device_details).to_excel(writer, sheet_name="Detail Perangkat", index=False)
    output.seek(0)
    filename = f"rekap_sti_{period.year}_{period.month:02d}.xlsx" if period else "rekap_sti_kumulatif.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Permintaan tidak valid."), particles_enabled=False), 400


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="Halaman atau data yang Anda cari tidak ditemukan.", particles_enabled=False), 404


@app.errorhandler(413)
def file_too_large(error):
    return render_template("error.html", code=413, message="Ukuran file terlalu besar. Maksimal upload 3 MB.", particles_enabled=False), 413


with app.app_context():
    db.create_all()
    seed_database()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
