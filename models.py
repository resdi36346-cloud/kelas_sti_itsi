from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    nim = db.Column(db.String(30), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="mahasiswa", index=True)

    name = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(20), nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    origin = db.Column(db.String(120), nullable=True)
    position = db.Column(db.String(80), nullable=True, default="Anggota")
    hobbies = db.Column(db.String(255), nullable=True)
    motto = db.Column(db.String(255), nullable=True)
    instagram = db.Column(db.String(120), nullable=True)
    linkedin = db.Column(db.String(180), nullable=True)
    tiktok = db.Column(db.String(120), nullable=True)
    photo = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    kas_entries = db.relationship(
        "KasBulanan", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def initials(self) -> str:
        parts = [part for part in (self.name or "").split() if part]
        return "".join(part[0].upper() for part in parts[:2]) or "ST"

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class KasBulanan(db.Model):
    __tablename__ = "kas_bulanan"
    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uq_kas_user_year_month"),
        CheckConstraint("month >= 1 AND month <= 12", name="ck_kas_month_range"),
        CheckConstraint(
            "amount_due >= 0 AND amount_paid >= 0",
            name="ck_kas_amount_nonnegative",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    year = db.Column(db.Integer, nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False)
    amount_due = db.Column(db.Integer, nullable=False, default=20000)
    amount_paid = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="Belum Bayar")
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = db.relationship("User", back_populates="kas_entries")

    @property
    def balance(self) -> int:
        return max(0, (self.amount_due or 0) - (self.amount_paid or 0))


class PeriodePenilaian(db.Model):
    __tablename__ = "periode_penilaian"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    week_number = db.Column(db.Integer, nullable=False, default=1)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)


class PenilaianSikap(db.Model):
    __tablename__ = "penilaian_sikap"
    __table_args__ = (
        UniqueConstraint(
            "periode_id",
            "penilai_id",
            "dinilai_id",
            name="uq_penilaian_periode_penilai_dinilai",
        ),
        CheckConstraint("kedisiplinan BETWEEN 1 AND 5", name="ck_kedisiplinan_range"),
        CheckConstraint("kerja_sama BETWEEN 1 AND 5", name="ck_kerjasama_range"),
        CheckConstraint("etika_komunikasi BETWEEN 1 AND 5", name="ck_etika_range"),
        CheckConstraint("tanggung_jawab BETWEEN 1 AND 5", name="ck_tanggungjawab_range"),
    )

    id = db.Column(db.Integer, primary_key=True)
    periode_id = db.Column(
        db.Integer,
        db.ForeignKey("periode_penilaian.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    penilai_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dinilai_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kedisiplinan = db.Column(db.Integer, nullable=False)
    kerja_sama = db.Column(db.Integer, nullable=False)
    etika_komunikasi = db.Column(db.Integer, nullable=False)
    tanggung_jawab = db.Column(db.Integer, nullable=False)
    catatan = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    periode = db.relationship("PeriodePenilaian")
    penilai = db.relationship("User", foreign_keys=[penilai_id])
    dinilai = db.relationship("User", foreign_keys=[dinilai_id])

    @property
    def average_score(self) -> float:
        scores = [
            self.kedisiplinan,
            self.kerja_sama,
            self.etika_komunikasi,
            self.tanggung_jawab,
        ]
        return round(sum(scores) / len(scores), 2)


class PerangkatKelas(db.Model):
    """Jabatan/peran perangkat kelas yang dapat dikelola admin."""
    __tablename__ = "perangkat_kelas"

    id = db.Column(db.Integer, primary_key=True)
    jabatan = db.Column(db.String(100), nullable=False, index=True)
    holder_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deskripsi = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    holder = db.relationship("User", foreign_keys=[holder_id])


class PenilaianKinerjaPerangkat(db.Model):
    """Evaluasi anonim kinerja satu jabatan perangkat kelas per periode."""
    __tablename__ = "penilaian_kinerja_perangkat"
    __table_args__ = (
        UniqueConstraint(
            "periode_id",
            "penilai_id",
            "perangkat_id",
            name="uq_kinerja_periode_penilai_perangkat",
        ),
        CheckConstraint("kedisiplinan BETWEEN 1 AND 5", name="ck_kinerja_disiplin_range"),
        CheckConstraint("tanggung_jawab BETWEEN 1 AND 5", name="ck_kinerja_tanggungjawab_range"),
        CheckConstraint("kepemimpinan BETWEEN 1 AND 5", name="ck_kinerja_kepemimpinan_range"),
        CheckConstraint("komunikasi BETWEEN 1 AND 5", name="ck_kinerja_komunikasi_range"),
        CheckConstraint("pelaksanaan_tugas BETWEEN 1 AND 5", name="ck_kinerja_tugas_range"),
    )

    id = db.Column(db.Integer, primary_key=True)
    periode_id = db.Column(
        db.Integer,
        db.ForeignKey("periode_penilaian.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    perangkat_id = db.Column(
        db.Integer,
        db.ForeignKey("perangkat_kelas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    penilai_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Snapshot menjaga riwayat tetap benar walau admin mengganti pemegang jabatan.
    holder_id_snapshot = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    jabatan_snapshot = db.Column(db.String(100), nullable=False)
    holder_name_snapshot = db.Column(db.String(120), nullable=False)
    holder_nim_snapshot = db.Column(db.String(30), nullable=True)
    holder_photo_snapshot = db.Column(db.String(255), nullable=True)

    kedisiplinan = db.Column(db.Integer, nullable=False)
    tanggung_jawab = db.Column(db.Integer, nullable=False)
    kepemimpinan = db.Column(db.Integer, nullable=False)
    komunikasi = db.Column(db.Integer, nullable=False)
    pelaksanaan_tugas = db.Column(db.Integer, nullable=False)
    catatan = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    periode = db.relationship("PeriodePenilaian")
    perangkat = db.relationship("PerangkatKelas")
    penilai = db.relationship("User", foreign_keys=[penilai_id])
    holder_snapshot = db.relationship("User", foreign_keys=[holder_id_snapshot])

    @property
    def average_score(self) -> float:
        scores = [
            self.kedisiplinan,
            self.tanggung_jawab,
            self.kepemimpinan,
            self.komunikasi,
            self.pelaksanaan_tugas,
        ]
        return round(sum(scores) / len(scores), 2)


class PortalSetting(db.Model):
    """Penanda migrasi/seeding agar data kelas tidak ditimpa saat aplikasi restart."""
    __tablename__ = "portal_settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class GroupSet(db.Model):
    """Satu hasil pembagian kelompok untuk mata kuliah tertentu."""
    __tablename__ = "group_sets"

    id = db.Column(db.Integer, primary_key=True)
    course = db.Column(db.String(120), nullable=False)
    topic = db.Column(db.String(180), nullable=True)
    group_count = db.Column(db.Integer, nullable=False)
    members_per_group = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    members = db.relationship(
        "GroupMember", back_populates="group_set", cascade="all, delete-orphan",
        order_by="GroupMember.group_number, GroupMember.position"
    )
    creator = db.relationship("User", foreign_keys=[created_by])


class GroupMember(db.Model):
    """Mahasiswa yang masuk ke suatu kelompok dalam hasil pembagian."""
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_set_id", "user_id", name="uq_group_set_student"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_set_id = db.Column(db.Integer, db.ForeignKey("group_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_number = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)

    group_set = db.relationship("GroupSet", back_populates="members")
    student = db.relationship("User", foreign_keys=[user_id])


class GalleryPhoto(db.Model):
    """Foto album publik yang dapat dikelola administrator."""
    __tablename__ = "gallery_photos"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    caption = db.Column(db.String(500), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    is_public = db.Column(db.Boolean, nullable=False, default=True, index=True)
    uploaded_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    uploader = db.relationship("User", foreign_keys=[uploaded_by])


class LoginMedia(db.Model):
    """Video intro halaman login yang dapat dikelola administrator."""
    __tablename__ = "login_media"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    video_filename = db.Column(db.String(255), nullable=False, unique=True)
    poster_filename = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False, index=True)
    uploaded_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    uploader = db.relationship("User", foreign_keys=[uploaded_by])
