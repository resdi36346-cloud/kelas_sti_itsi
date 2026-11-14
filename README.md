# Portal Kelas STI-A – ITSI

Portal manajemen kelas Program Studi Sistem dan Teknologi Informasi, Institut Teknologi Sawit Indonesia. Dibangun dengan Python/Flask, Flask-SQLAlchemy, SQLite, Flask-Login, Tailwind CSS CDN, JavaScript, Chart.js, Lucide, tsParticles, Pandas, dan OpenPyXL.

## Menjalankan di Windows / VS Code

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000`. Database `kelas_sti.db` dibuat otomatis. `db.create_all()` menambah tabel baru jika proyek versi sebelumnya sudah memiliki database. Jangan hapus file database atau `static/uploads` jika ingin mempertahankan data/foto.

## Login awal

- Admin: `admin` / `admin12345` (segera ganti lewat menu Akun Admin).
- Mahasiswa: login dengan NIM atau username `m` + NIM, password awal `123456`.

## Fitur halaman publik

- Beranda memuat ringkasan kelas, kas bulan berjalan, peringkat sikap bulanan, dan peringkat kinerja perangkat kelas.
- Menu Direktori membuka grid mahasiswa; setiap kartu membuka halaman biodata dengan foto profil besar di tengah.
- Menu Transparansi Uang Kas membuka matriks 12 bulan per mahasiswa.
- Shortcut Pembagian Kelompok membuka daftar mata kuliah, materi, kelompok, dan anggota tanpa perlu login.

## Fitur penilaian bulanan

- Satu periode digunakan untuk satu bulan kalender. Dalam bulan yang sama admin tidak dapat membuat periode kedua; penilaian teman dan perangkat mengikuti periode tersebut.

## Fitur mahasiswa

- Dashboard hanya ringkasan dan shortcut menu.
- Penilaian sikap kepada 29 rekan sekelas, satu kali per orang setiap bulan.
- Penilaian kinerja perangkat kelas (Askel, Mandor, dan jabatan dinamis lain), satu kali per jabatan setiap bulan.
- Rapor radar, catatan anonim, dan hasil penilaian jabatan yang sedang dipegang.
- Pengaturan foto, hobi, moto, akun sosial, serta password. Biodata inti hanya dapat diubah admin.
- Menu Kelompok Mata Kuliah menampilkan pembagian kelompok yang dibuat admin.

## Fitur admin

- Dashboard ringkasan dan halaman terpisah untuk Periode, Rekap Nilai, Perangkat Kelas, Uang Kas, Mahasiswa, Acak Kelompok, dan Akun Admin.
- Penilaian perangkat menampilkan jabatan/pemegang yang dinilai, skor lima aspek, serta kesan dan saran. Identitas pemberi penilaian tidak ditampilkan agar anonimitas tetap terjaga.
- Pengelolaan kas menggunakan satu tombol simpan massal untuk semua mahasiswa pada bulan terpilih. Status “Belum dicatat” menghapus/menjaga baris tetap kosong.
- Pengelolaan mahasiswa memakai satu tombol simpan untuk perubahan biodata inti banyak mahasiswa sekaligus; reset password dan hapus akun tetap tersedia per baris.
- Pengacak kelompok berdasarkan mata kuliah, materi, jumlah kelompok, dan kapasitas anggota; admin dapat menambah, memindahkan, atau mengeluarkan anggota secara manual. Hasil tersimpan dan dapat dilihat di dashboard publik maupun mahasiswa.
- Export rekap nilai sikap dan perangkat ke Excel.

## Tema dan tampilan

Pilih Hijau Agri-Tech, Biru Cyber, Putih Minimalis, atau Black Space. Tema disimpan di browser. Black Space menampilkan animasi bintang bergerak. Tata letak memakai grid responsif agar nyaman di desktop dan smartphone. Jam digital mengikuti waktu lokal perangkat yang membuka portal.

## Data kas 2026

Untuk 30 mahasiswa STI-A yang diberikan: Januari–September kosong, Oktober lunas untuk semua mahasiswa, November–Desember belum dicatat. Seeder menandai pembaruan roster/kas satu kali agar perubahan admin tidak ditimpa setiap restart.

## Catatan keamanan

- Password di-hash dengan Werkzeug.
- Form POST memakai CSRF token.
- Constraint unik mencegah penilaian ganda pada periode yang sama.
- Untuk penggunaan online/produksi, tetapkan `SECRET_KEY` kuat melalui environment variable, gunakan HTTPS dan server WSGI, batasi akses admin, dan backup database secara rutin.
- Tailwind CDN, Chart.js, Lucide, Google Fonts, dan tsParticles memerlukan koneksi internet pada browser.
