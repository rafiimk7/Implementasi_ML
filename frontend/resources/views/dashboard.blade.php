<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Prediksi ATM</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="bg-gray-100 min-h-screen font-sans">

    {{-- NAVBAR --}}
    <nav class="bg-blue-800 text-white shadow-md">
        <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <svg class="w-7 h-7 text-blue-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/>
                </svg>
                <span class="text-xl font-semibold tracking-wide">Prediksi ATM</span>
            </div>
        </div>
    </nav>

    <div class="max-w-7xl mx-auto px-4 py-8">

        {{-- HEADER --}}
        <div class="mb-6">
            <h1 class="text-2xl font-bold text-gray-800">Dashboard Prediksi Tanggal Habis Saldo ATM</h1>
            <p class="text-gray-500 mt-1 text-sm">Monitoring prediksi saldo ATM berbasis machine learning.<strong class="text-gray-600"Klik></p>
        </div>

        @php
            // Ambil data dari variabel $prediction (sesuai dengan response dari controller)
            $data      = $prediction['data'] ?? [];
            $total     = $prediction['count'] ?? count($data);
            $lastUpdate = $prediction['last_update'] ?? now()->format('d M Y, H:i');
            
            // Threshold berdasarkan business rule (sama dengan di predict_realtime.py)
            $kritisDay = 2;  // ATM kritis jika habis dalam <= 2 hari
            $waspDay   = 4;  // ATM waspada jika habis dalam <= 4 hari

            // Hitung statistik berdasarkan threshold
            $kritis  = collect($data)->filter(fn($r) => isset($r['prediksi_hari']) && $r['prediksi_hari'] <= $kritisDay)->count();
            $waspada = collect($data)->filter(fn($r) => isset($r['prediksi_hari']) && $r['prediksi_hari'] > $kritisDay && $r['prediksi_hari'] <= $waspDay)->count();
            $aman    = collect($data)->filter(fn($r) => isset($r['prediksi_hari']) && $r['prediksi_hari'] > $waspDay)->count();

            // Rata-rata prediksi hari
            $rataHari = $total > 0
                ? round(collect($data)->avg(fn($r) => $r['prediksi_hari'] ?? 0), 1)
                : 0;

            // Rata-rata sisa pagu
            $rataPagu = $total > 0
                ? round(collect($data)->avg(fn($r) => $r['sisa_pagu'] ?? 0), 0)
                : 0;
        @endphp

        {{-- SUMMARY CARDS --}}
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
            {{-- Total ATM --}}
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex items-center gap-4">
                <div class="bg-blue-100 rounded-full p-3">
                    <svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                    </svg>
                </div>
                <div>
                    <p class="text-xs text-gray-500 uppercase tracking-wide">Total ATM</p>
                    <p class="text-2xl font-bold text-gray-800">{{ $total }}</p>
                </div>
            </div>

            {{-- Rata-rata Sisa Pagu --}}
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex items-center gap-4">
                <div class="bg-purple-100 rounded-full p-3">
                    <svg class="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                </div>
                <div>
                    <p class="text-xs text-gray-500 uppercase tracking-wide">Rata-rata Sisa Pagu</p>
                    <p class="text-2xl font-bold text-gray-800">{{ number_format($rataPagu, 0, ',', '.') }}</p>
                </div>
            </div>

            {{-- Kritis --}}
            <div class="bg-white rounded-xl shadow-sm border border-red-200 p-5 flex items-center gap-4">
                <div class="bg-red-100 rounded-full p-3">
                    <svg class="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                    </svg>
                </div>
                <div>
                    <p class="text-xs text-red-500 uppercase tracking-wide">Kritis (≤ {{ $kritisDay }} hari)</p>
                    <p class="text-2xl font-bold text-red-600">{{ $kritis }}</p>
                </div>
            </div>

            {{-- Waspada --}}
            <div class="bg-white rounded-xl shadow-sm border border-yellow-200 p-5 flex items-center gap-4">
                <div class="bg-yellow-100 rounded-full p-3">
                    <svg class="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>
                    </svg>
                </div>
                <div>
                    <p class="text-xs text-yellow-600 uppercase tracking-wide">Waspada (≤ {{ $waspDay }} hari)</p>
                    <p class="text-2xl font-bold text-yellow-600">{{ $waspada }}</p>
                </div>
            </div>

            {{-- Aman --}}
            <div class="bg-white rounded-xl shadow-sm border border-green-200 p-5 flex items-center gap-4">
                <div class="bg-green-100 rounded-full p-3">
                    <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                </div>
                <div>
                    <p class="text-xs text-green-600 uppercase tracking-wide">Aman (> {{ $waspDay }} hari)</p>
                    <p class="text-2xl font-bold text-green-600">{{ $aman }}</p>
                </div>
            </div>
        </div>

        {{-- TABEL DATA --}}
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">

            {{-- Table Header --}}
            <div class="px-6 py-4 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                    <h2 class="text-base font-semibold text-gray-800">Data Prediksi ATM</h2>
                    <p class="text-xs text-gray-400 mt-0.5">
                        Rata-rata sisa waktu: <span class="font-semibold text-gray-600">{{ $rataHari }} hari</span>
                        &nbsp;|&nbsp; 
                    </p>
                </div>
                <div class="flex items-center gap-2">
                    <input
                        type="text"
                        id="searchInput"
                        placeholder="Cari TID..."
                        class="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 w-48"
                        onkeyup="filterTable()"
                    >
                    <select id="filterStatus" class="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400" onchange="filterTable()">
                        <option value="all">Semua Status</option>
                        <option value="kritis">🔴 Kritis</option>
                        <option value="waspada">🟠 Waspada</option>
                        <option value="aman">🟢 Aman</option>
                    </select>
                </div>
            </div>

            @if(empty($data))
                {{-- Empty State --}}
                <div class="py-16 text-center">
                    <svg class="w-12 h-12 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <p class="text-gray-400 font-medium">Tidak ada data prediksi.</p>
                    <p class="text-gray-400 text-sm mt-1">Pastikan backend berjalan dan model sudah dilatih.</p>
                </div>
            @else
                {{-- Table --}}
                <div class="overflow-x-auto">
                    <table class="w-full text-sm" id="predictionTable">
                        <thead>
                            <tr class="bg-gray-50 text-gray-500 uppercase text-xs tracking-wider">
                                <th class="px-4 py-3 text-left font-semibold">#</th>
                                <th class="px-4 py-3 text-left font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(1)">TID ↕</th>
                                <th class="px-4 py-3 text-left font-semibold">Updated</th>
                                <th class="px-4 py-3 text-right font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(3)">Total LMB ↕</th>
                                <th class="px-4 py-3 text-right font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(4)">Pagu Existing ↕</th>
                                <th class="px-4 py-3 text-right font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(5)">Sisa Pagu ↕</th>
                                <th class="px-4 py-3 text-right font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(6)">Rata Harian ↕</th>
                                <th class="px-4 py-3 text-right font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(7)">Prediksi Hari ↕</th>
                                <th class="px-4 py-3 text-center font-semibold cursor-pointer hover:text-blue-600" onclick="sortTable(8)">Tanggal Habis ↕</th>
                                <th class="px-4 py-3 text-center font-semibold">Status</th>
                                <th class="px-4 py-3 text-center font-semibold">Update Prediksi</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100" id="tableBody">
                            @foreach($data as $i => $row)
                                @php
                                    $hari = $row['prediksi_hari'] ?? null;
                                    if ($hari === null) {
                                        $status = 'unknown';
                                        $badgeClass = 'bg-gray-100 text-gray-500';
                                        $rowClass   = '';
                                        $label      = 'N/A';
                                    } elseif ($hari <= $kritisDay) {
                                         $status = 'kritis';
                                        $badgeClass = 'bg-red-100 text-red-700';
                                        $rowClass   = 'bg-red-50';
                                        $label      = '🔴 Kritis';
                                    } elseif ($hari <= $waspDay) {
                                        $status = 'waspada';
                                        $badgeClass = 'bg-yellow-100 text-yellow-700';
                                        $rowClass   = 'bg-yellow-50';
                                        $label      = '🟠 Waspada';
                                    } else {
                                        $status = 'aman';
                                        $badgeClass = 'bg-green-100 text-green-700';
                                        $rowClass   = '';
                                        $label      = '🟢 Aman';
                                    }
                                @endphp
                                <tr class="hover:bg-blue-50 transition-colors {{ $rowClass }}" data-status="{{ $status }}">
                                    <td class="px-4 py-3 text-gray-400">{{ $i + 1 }}</td>
                                    <td class="px-4 py-3 font-mono font-semibold text-blue-700 tracking-wide">
                                        {{ $row['tid'] ?? '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-gray-600 text-sm">
                                        {{ $row['updated'] ?? '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-right font-medium text-gray-700">
                                        {{ isset($row['total_lmb']) ? number_format($row['total_lmb'], 0, ',', '.') : '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-right font-medium text-gray-700">
                                        {{ isset($row['pagu_existing']) ? number_format($row['pagu_existing'], 0, ',', '.') : '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-right font-medium text-gray-700">
                                        {{ isset($row['sisa_pagu']) ? number_format($row['sisa_pagu'], 0, ',', '.') : '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-right text-gray-500">
                                        {{ $row['ratas_harian'] ?? '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-right">
                                        @if($hari !== null)
                                            <span class="font-bold {{ $hari <= $kritisDay ? 'text-red-600' : ($hari <= $waspDay ? 'text-yellow-600' : 'text-gray-700') }}">
                                                {{ $hari }} hari
                                            </span>
                                        @else
                                            <span class="text-gray-400">-</span>
                                        @endif
                                    </td>
                                    <td class="px-4 py-3 text-center font-medium text-gray-700">
                                        {{ $row['tanggal_habis'] ?? '-' }}
                                    </td>
                                    <td class="px-4 py-3 text-center">
                                        <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold {{ $badgeClass }}">
                                            {{ $label }}
                                        </span>
                                    </td>
                                    <td class="px-4 py-3 text-center text-xs text-gray-400">
                                        {{ isset($row['prediksi_at'])
                                            ? \Carbon\Carbon::parse($row['prediksi_at'])->format('d/m/Y H:i')
                                            : '-' }}
                                    </td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>

                {{-- Table Footer --}}
                <div class="px-6 py-3 border-t border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-gray-400">
                    <span id="rowCount">Menampilkan {{ count($data) }} dari {{ $total }} ATM</span>
                    <div class="flex items-center gap-3">
                        <span class="inline-flex items-center gap-1.5">
                            <span class="inline-block w-2 h-2 rounded-full bg-red-500"></span> Kritis (≤ {{ $kritisDay }} hari)
                        </span>
                        <span class="inline-flex items-center gap-1.5">
                            <span class="inline-block w-2 h-2 rounded-full bg-yellow-500"></span> Waspada (≤ {{ $waspDay }} hari)
                        </span>
                        <span class="inline-flex items-center gap-1.5">
                            <span class="inline-block w-2 h-2 rounded-full bg-green-500"></span> Aman (> {{ $waspDay }} hari)
                        </span>
                    </div>
                </div>
            @endif
        </div>

        {{-- Tambahan: Informasi Model --}}
        <div class="mt-6 bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
                <div class="flex items-center gap-4">
                    <span class="font-medium text-gray-700">ℹ️ Informasi Sistem</span>
                    <span>Model: <span class="font-mono text-gray-600">RandomForestRegressor</span></span>
                    <span>Jumlah Fitur: <span class="font-mono text-gray-600">14</span></span>
                </div>
            </div>
        </div>

    </div>

    {{-- FOOTER --}}
    <footer class="text-center text-xs text-gray-400 py-6">
        &copy; {{ date('Y') }} Sistem Prediksi ATM &mdash; Powered by Laravel + FastAPI
    </footer>

    <script>
        // ─── FILTER & SORT ────────────────────────────────────────
        function filterTable() {
            const search = document.getElementById('searchInput').value.toLowerCase();
            const status = document.getElementById('filterStatus').value;
            const rows   = document.querySelectorAll('#tableBody tr');
            let visible  = 0;

            rows.forEach(row => {
                const tid       = row.querySelector('td:nth-child(2)')?.textContent.toLowerCase() ?? '';
                const rowStatus = row.dataset.status ?? '';
                const matchTid  = tid.includes(search);
                const matchStat = status === 'all' || rowStatus === status;

                if (matchTid && matchStat) {
                    row.style.display = '';
                    visible++;
                } else {
                    row.style.display = 'none';
                }
            });

            document.getElementById('rowCount').textContent =
                `Menampilkan ${visible} dari ${rows.length} ATM`;
        }

        let sortDir = {};
        function sortTable(colIndex) {
            const tbody = document.getElementById('tableBody');
            const rows  = Array.from(tbody.querySelectorAll('tr'));
            const dir   = (sortDir[colIndex] = !(sortDir[colIndex] ?? false));

            rows.sort((a, b) => {
                const aText = a.querySelector(`td:nth-child(${colIndex + 1})`)?.textContent.trim() ?? '';
                const bText = b.querySelector(`td:nth-child(${colIndex + 1})`)?.textContent.trim() ?? '';
                const aNum  = parseFloat(aText.replace(/[^0-9.-]/g, ''));
                const bNum  = parseFloat(bText.replace(/[^0-9.-]/g, ''));

                if (!isNaN(aNum) && !isNaN(bNum)) return dir ? aNum - bNum : bNum - aNum;
                return dir ? aText.localeCompare(bText) : bText.localeCompare(aText);
            });

            rows.forEach(r => tbody.appendChild(r));
        }
    </script>

</body>
</html>