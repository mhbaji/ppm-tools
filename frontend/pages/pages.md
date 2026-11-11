# Pekerjaan Tampilan

## Struktur halaman
- Semua dokumen HTML disimpan di `frontend/pages/`; aset CSS dan JavaScript tetap di `frontend/css/` dan `frontend/js/`.
- Nama berkas halaman dan skrip menggunakan bahasa Inggris. URL publik/admin yang sudah dipakai klien tetap dipertahankan untuk kompatibilitas.
- Layout menyesuaikan layar kecil mulai lebar 320 px; tabel panjang menggunakan area gulir horizontal.

## Admin / Dashboard
- [x] Menampilkan jumlah sub kegiatan, jumlah jenis tagging, dan daftar jenis tagging.
- [x] Merinci setiap jenis tagging dengan jumlah OPD, sub kegiatan, dan anggaran.
- [x] Menyediakan pilihan tahun dan tahapan, dengan tahun saat ini dipilih jika tersedia.
- [x] Menyediakan pemilih multi-subunit khusus unduhan; tanpa pilihan, semua subunit diekspor.
- [x] Membatasi tingkat rincian publik hingga Paket/Kelompok dan menyembunyikan baris rekening.

## Publik / Realisasi dan Capaian
- [x] Menyediakan filter tahun, periode, dan beberapa subunit.
- [x] Memperjelas pemilihan beberapa subunit dan menata kartu ringkasan.
- [x] Menyediakan pencarian, sorting, pagination, ringkasan, serta ekspor Excel/PDF.
- [x] Menampilkan capaian hanya pada level Program dan Sub Unit.

## Publik / Tautan
- [x] Menampilkan topik utama, hingga lima topik rincian terbaru, serta tautan aktif.
- [x] Menampilkan deskripsi, gambar, tag, dan tanggal publikasi.
- [x] Menyediakan pencarian seluruh topik dan tautan aktif, dengan hasil yang menunjukkan hierarki topiknya.
- [x] Menampilkan ringkasan topik utama, kartu subtopik, dan kartu tautan.
- [x] Menampilkan tanggal publikasi di atas judul kartu tautan.

## Admin / Tautan
- [x] Mengelola topik utama dan topik rincian.
- [x] Mengelola tautan dengan status aktif/nonaktif dan batas hak edit/hapus berdasarkan pembuat.
- [x] Menyediakan pencarian daftar topik dan tautan.
- [x] Menata form topik dan tautan berdampingan pada layar lebar serta bertumpuk pada layar sempit.

## Publik / Navigasi dan Perbandingan Anggaran
- [x] Menyamakan susunan navigasi publik serta menandai halaman aktif dengan gaya konsisten.
- [x] Membatasi rincian Dashboard dan Perbandingan Anggaran sampai Paket/Kelompok.
- [x] Menerapkan pilihan tahun/sumber Perbandingan Anggaran hanya setelah tombol Tampilkan ditekan.
- [x] Menghapus opsi semua tahun dari pilihan sumber Perbandingan Anggaran.

## Admin / Sub Kegiatan
- [x] Menyediakan form unggah Excel dan pilihan tahun.
- [x] Menampilkan pilihan tahun dan tahapan; tahun saat ini dipilih bila tersedia, selain itu placeholder `Pilih Tahun`.
- [x] Menampilkan ringkasan jumlah SKPD, program, kegiatan, dan sub kegiatan.
- [x] Menampilkan tabel kode, hierarki, pagu, dan sumber dana.
- [x] Mendukung buka/tutup rincian sampai tingkat rekening.
- [x] Impor selalu membuat tahapan baru; data tahapan lama tidak diganti.

## Admin / Jenis Tagging
- [x] Menyediakan form tambah dengan kode otomatis dan pilihan tahun.
- [x] Menolak nama jenis tagging duplikat pada tahun yang sama.
- [x] Menampilkan kode, nama, tahun, serta aksi edit dan hapus.

## Admin / Tagging Sub Kegiatan
- [x] Menyediakan unggah Excel, pilihan tahun, dan jenis tagging.
- [x] Menampilkan pilihan semua jenis tagging dan menyaring daftar berdasarkan pilihan.
- [x] Menyediakan pencarian kode/nama dan pagination 10, 25, 50, atau 100 baris (default 10).
- [x] Menyusun filter dalam satu baris pada layar lebar.
- [x] Menampilkan ringkasan jumlah sub kegiatan.

# Pekerjaan API

## Catatan kebutuhan API
- Dashboard menggunakan `GET /api/years`, `GET /api/tahapan`, dan `GET /api/tagging-summary`. Ringkasan mengembalikan total sub kegiatan, total yang belum ditagging, dan per jenis tagging: jumlah OPD, sub kegiatan, dan pagu.
- Sub Kegiatan menggunakan `GET /api/anggaran` untuk data hierarki, `GET /api/admin/sub-kegiatan/summary` untuk jumlah SKPD/program/kegiatan/sub kegiatan, dan `POST /api/admin/sub-kegiatan/import` untuk impor Excel ke tahapan baru. Workbook berisi kolom referensi APBD dan `PAGU`; nilai tahun dari form diterapkan ke impor.
- Jenis Tagging menggunakan `GET/POST /api/admin/tagging-types`, `PATCH /api/admin/tagging-types/<code>`, dan `DELETE /api/admin/tagging-types/<code>`. Nama duplikat pada tahun yang sama ditolak.
- Tagging Sub Kegiatan menggunakan `GET/PUT /api/admin/tagging-sub-kegiatan` dan `POST /api/admin/tagging-sub-kegiatan/import`. File impor tagging harus memiliki kolom `KODE SUB KEGIATAN`; penandaan lain tidak dihapus.
- Semua mutasi admin memerlukan autentikasi dan token CSRF. API tagging lama tetap dipertahankan sebagai alias.
- Blueprint `pages`, `public`, dan `admin` dipisahkan sesuai tujuan; helper dan handler error bersama berada di modul routes.

## Status API
- [x] Mencatat kontrak API tiap tampilan admin.
- [x] Menyediakan API modular untuk dashboard, sub kegiatan, jenis tagging, dan tagging sub kegiatan.
- [x] Memvalidasi workbook, tahun, tahapan, serta referensi sebelum menyimpan impor.
- [x] Mencegah penggantian data APBD lama saat impor; tiap impor menambahkan tahapan baru.

# Pekerjaan JavaScript
- [x] Mengintegrasikan API dashboard dan menampilkan ringkasan rinci.
- [x] Mengintegrasikan API Sub Kegiatan, impor file, ringkasan, dan hierarki yang dapat dibuka/tutup.
- [x] Mengintegrasikan API CRUD Jenis Tagging.
- [x] Mengintegrasikan API pencarian, filter, pagination, simpan, dan impor Tagging Sub Kegiatan.

# Catatan Implementasi
- Ekspor workbook Excel Dashboard dibuat server melalui `/api/anggaran`; ekspor Tagging dan Perbandingan Anggaran dibuat di browser, sedangkan Realisasi memakai ekspor server terfilter. PDF menggunakan alur cetak browser.
- File impor Sub Kegiatan dan Tagging Sub Kegiatan disimpan di `data/admin_uploads`; tabel `admin_upload` hanya menyimpan metadata dan URL. `GET /api/admin/uploads` mendukung pencarian serta pagination 10/25/50/100, URL file memerlukan autentikasi admin, dan `DELETE /api/admin/uploads/<id>` menghapus metadata beserta file storage.
- Halaman dan endpoint Dinamisasi Anggaran tidak didaftarkan; file sumber tetap dipertahankan dan tautan navigasinya dihapus.
- Perbandingan Anggaran memulai dua sumber. Pemilihan sumber Tagging menampilkan pilihan Tahapan dan mengirim pilihan tersebut ke API.
- Dashboard Admin menampilkan realisasi anggaran dan persentase realisasi; metrik sub kegiatan belum ditagging tidak lagi ditampilkan.
- Tabel Perangkat Daerah menggunakan lebar konten dan overflow horizontal pada viewport sempit.
- Database default berada di `data/ppm_tools.sqlite3`. Saat pertama kali berpindah dari database lama, aplikasi menyalin datanya dan mempertahankan database asal sebagai cadangan; nama tabel dan kolom disimpan dalam bahasa Inggris.
