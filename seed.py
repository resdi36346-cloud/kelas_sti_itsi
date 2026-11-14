"""Seed data Portal Kelas STI – ITSI.

Roster versi 2 mengganti 30 akun dummy sebelumnya dengan daftar resmi yang
dikirimkan pengguna. Penanda PortalSetting membuat pembaruan hanya berjalan
sekali sehingga perubahan biodata/kas oleh admin tidak tertimpa saat restart.
"""
from datetime import date, datetime

from models import db, User, KasBulanan, PeriodePenilaian, PortalSetting


STUDENTS = [
    ("260203001", "AGUNG KURNIA DARMA"),
    ("260203002", "ALDO TRIALDI RAMBE"),
    ("260203003", "ANDIKKA RAMADHAN"),
    ("260203004", "ANGEL TIONA LIMBONG"),
    ("260203005", "ANGGUN AYU LESTARI SITINJAK"),
    ("260203006", "ARIS RAMBE"),
    ("260203007", "CHAIRI BUNGA LESTARI"),
    ("260203008", "DANIEL PURBA"),
    ("260203009", "DINDA LESTARI"),
    ("260203010", "DITA WELDA MAWANY"),
    ("260203011", "ERLANDO"),
    ("260203012", "FAHRI AFRIAN"),
    ("260203013", "FRANS HAYDEN MANIK"),
    ("260203014", "FREDERIK BENIGDICTA JULIAN WAHYUDI"),
    ("260203015", "HALWA RATU A'TIKAH"),
    ("260203016", "JESSIKA YOSEPHA BR PURBA"),
    ("260203017", "MANNA GITA SALSALINA BR GINTING"),
    ("260203018", "MARFAN ALEXANDER KASI"),
    ("260203019", "MEI SAROHA"),
    ("260203020", "MELANDRE IVANI"),
    ("260203021", "M. RAFIF SYARAHIL"),
    ("260203022", "MUSLIMAH HASIBUAN"),
    ("260203023", "NUR INDAH DAMAYANTI"),
    ("260203024", "RAFFI AHMAD BM"),
    ("260203025", "SHAKI GIFFARY"),
    ("260203026", "STEVANI KHOIRUNISA JAMBAK"),
    ("260203027", "WADI MUHAMMAD SYARIP"),
    ("260203028", "WAHYUDI ANUGRAH"),
    ("260203029", "ZASKIA PUTRI SITUMORANG"),
    ("260203030", "ZHEN NELGLIS DANI"),
]


def _setting_exists(key):
    return db.session.get(PortalSetting, key) is not None


def seed_database():
    """Buat admin, perbarui roster 30 mahasiswa satu kali, dan inisialisasi kas."""
    admin = User.query.filter_by(username="admin").first()
    if admin is None:
        admin = User(
            username="admin",
            name="Administrator STI",
            role="admin",
            position="Administrator",
            origin="Institut Teknologi Sawit Indonesia",
        )
        admin.set_password("admin12345")
        db.session.add(admin)

    if not _setting_exists("roster_sti_2026_v2"):
        for nim, name in STUDENTS:
            student = User.query.filter_by(nim=nim).first()
            if student is None:
                student = User(
                    username=f"m{nim}",
                    nim=nim,
                    name=name,
                    role="mahasiswa",
                    position="Anggota",
                )
                student.set_password("123456")
                db.session.add(student)
            else:
                student.username = f"m{nim}"
                student.name = name
                student.role = "mahasiswa"
                student.position = student.position or "Anggota"
                # Data yang belum diberikan pengguna tetap kosong untuk dilengkapi admin.
                student.gender = None
                student.birth_date = None
                student.origin = None
                student.hobbies = None
                student.motto = None
                student.instagram = None
                student.linkedin = None
                student.tiktok = None
                # Foto yang sudah diunggah tidak dihapus.
        db.session.add(PortalSetting(key="roster_sti_2026_v2", value="done"))

    db.session.flush()

    # Migrasi kas satu kali sesuai informasi mahasiswa baru angkatan 2026:
    # Jan–Sep kosong, Oktober lunas untuk seluruh mahasiswa, Nov–Des belum dicatat.
    if not _setting_exists("cash_2026_maba_october_v1"):
        students = User.query.filter_by(role="mahasiswa").all()
        student_ids = [student.id for student in students]
        if student_ids:
            KasBulanan.query.filter(
                KasBulanan.user_id.in_(student_ids),
                KasBulanan.year == 2026,
                KasBulanan.month != 10,
            ).delete(synchronize_session=False)
            for student in students:
                row = KasBulanan.query.filter_by(
                    user_id=student.id, year=2026, month=10
                ).first()
                if row is None:
                    row = KasBulanan(
                        user_id=student.id, year=2026, month=10,
                        amount_due=20000, amount_paid=20000, status="Lunas",
                    )
                    db.session.add(row)
                else:
                    row.amount_due = 20000
                    row.amount_paid = 20000
                    row.status = "Lunas"
        db.session.add(PortalSetting(key="cash_2026_maba_october_v1", value="done"))

    # Migrasi sesi lama: bila database sebelumnya berisi beberapa periode
    # mingguan dalam bulan yang sama, satu periode utama dipertahankan dan
    # sisanya ditandai sebagai arsip. Penilaian historis tidak dihapus.
    monthly_label_setting = PortalSetting.query.filter_by(key="monthly_period_label_v1").first()
    if not monthly_label_setting:
        month_names_for_period = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        ]
        periods_by_month = {}
        for period in PeriodePenilaian.query.order_by(
            PeriodePenilaian.created_at.asc(), PeriodePenilaian.id.asc()
        ).all():
            periods_by_month.setdefault((period.year, period.month), []).append(period)
        for (period_year, period_month), month_periods in periods_by_month.items():
            active_period = next((row for row in month_periods if row.is_active), None)
            primary_period = active_period or month_periods[-1]
            month_label = f"{month_names_for_period[period_month - 1]} {period_year}"
            for row in month_periods:
                if row.id == primary_period.id:
                    if row.name.startswith("Minggu ke-"):
                        row.name = month_label
                else:
                    if "(Arsip" not in (row.name or ""):
                        if row.name.startswith("Minggu ke-"):
                            row.name = f"{month_label} (Arsip minggu ke-{row.week_number})"
                        else:
                            row.name = f"{row.name} (Arsip lama)"
                    if row.is_active:
                        row.is_active = False
                        row.closed_at = row.closed_at or datetime.utcnow()
        db.session.add(PortalSetting(key="monthly_period_label_v1", value="done"))

    today = date.today()
    if PeriodePenilaian.query.count() == 0:
        month_names = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        ]
        db.session.add(PeriodePenilaian(
            name=f"{month_names[today.month - 1]} {today.year}",
            week_number=1,
            month=today.month,
            year=today.year,
            is_active=True,
        ))

    db.session.commit()


if __name__ == "__main__":
    from app import app

    with app.app_context():
        db.create_all()
        seed_database()
        print("Seeding selesai. Admin: admin / admin12345 | Mahasiswa: NIM / 123456")
