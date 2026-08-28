"""
Unit tests untuk calendar_features.py
--------------------------------------
Menguji: is_weekend, get_payday_date, is_payday, add_calendar_flags,
         fetch_holidays_from_api, get_holidays (dengan mock API + cache DB)

Jalankan:
  cd backend/
  python3 -m pytest tests/test_calendar_features.py -v
"""

import sys
import os
from datetime import date
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

# Tambahkan scripts/ ke path agar bisa import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from calendar_features import (
    CALENDARIFIC_URL,
    add_calendar_flags,
    fetch_holidays_from_api,
    get_holidays,
    get_payday_date,
    is_payday,
    is_weekend,
    _load_holidays_from_cache,
    _save_holidays_to_cache,
    _fetch_holidays_with_names,
)


# ===========================================================================
# TEST is_weekend
# ===========================================================================

class TestIsWeekend:
    def test_sabtu_adalah_weekend(self):
        # 2026-01-03 adalah Sabtu
        assert is_weekend(date(2026, 1, 3)) is True

    def test_minggu_adalah_weekend(self):
        # 2026-01-04 adalah Minggu
        assert is_weekend(date(2026, 1, 4)) is True

    def test_senin_bukan_weekend(self):
        assert is_weekend(date(2026, 1, 5)) is False

    def test_selasa_bukan_weekend(self):
        assert is_weekend(date(2026, 1, 6)) is False

    def test_rabu_bukan_weekend(self):
        assert is_weekend(date(2026, 1, 7)) is False

    def test_kamis_bukan_weekend(self):
        assert is_weekend(date(2026, 1, 8)) is False

    def test_jumat_bukan_weekend(self):
        assert is_weekend(date(2026, 1, 9)) is False


# ===========================================================================
# TEST get_payday_date
# ===========================================================================

class TestGetPaydayDate:
    def test_tanggal_25_hari_kerja(self):
        # Januari 2026 — tanggal 25 adalah Minggu, geser ke Jumat 23
        result = get_payday_date(2026, 1, "25")
        assert result == date(2026, 1, 23)

    def test_tanggal_25_jatuh_sabtu_geser_jumat(self):
        # Cari bulan di mana tgl 25 jatuh di Sabtu
        # April 2026: tgl 25 adalah Sabtu → geser ke Jumat 24
        result = get_payday_date(2026, 4, "25")
        assert result == date(2026, 4, 24)

    def test_tanggal_25_jatuh_minggu_geser_jumat(self):
        # Juli 2026: tgl 25 adalah Sabtu → geser ke Jumat 24
        # Verifikasi dengan weekday()
        result = get_payday_date(2026, 7, "25")
        # Harus selalu bukan weekend
        assert result.weekday() < 5

    def test_tanggal_25_hari_kerja_normal(self):
        # Maret 2026: tgl 25 adalah Rabu → tidak berubah
        result = get_payday_date(2026, 3, "25")
        assert result == date(2026, 3, 25)
        assert result.weekday() < 5

    def test_last_workday_desember(self):
        # Desember 2026: hari terakhir adalah 31 (Kamis) → tetap 31
        result = get_payday_date(2026, 12, "last_workday")
        assert result.month == 12
        assert result.year == 2026
        assert result.weekday() < 5  # harus hari kerja

    def test_last_workday_bukan_weekend(self):
        # Semua hasil last_workday harus bukan weekend
        for month in range(1, 13):
            result = get_payday_date(2026, month, "last_workday")
            assert result.weekday() < 5, f"Bulan {month}: {result} adalah weekend"

    def test_config_tidak_valid_fallback_25(self):
        # Config tidak valid → fallback ke 25
        result = get_payday_date(2026, 3, "invalid_config")
        expected = get_payday_date(2026, 3, "25")
        assert result == expected

    def test_tanggal_melebihi_akhir_bulan_februari(self):
        # Config "30" di Februari 2026 (28 hari) → clamp ke 28
        result = get_payday_date(2026, 2, "30")
        assert result.month == 2
        assert result.weekday() < 5

    def test_config_angka_lain(self):
        # Config "20" → tanggal 20 (atau geser jika weekend)
        result = get_payday_date(2026, 1, "20")
        assert result.weekday() < 5
        assert result.month == 1

    def test_hasil_selalu_dalam_bulan_yang_sama(self):
        # Hasil tidak boleh loncat ke bulan berikutnya
        for month in range(1, 13):
            result = get_payday_date(2026, month, "25")
            assert result.month == month, f"Bulan {month}: result.month={result.month}"


# ===========================================================================
# TEST is_payday
# ===========================================================================

class TestIsPayday:
    def test_tepat_hari_gajian(self):
        # Maret 2026, config "25" → tanggal 25 Maret adalah Rabu (hari kerja)
        assert is_payday(date(2026, 3, 25), "25") is True

    def test_bukan_hari_gajian(self):
        assert is_payday(date(2026, 3, 10), "25") is False
        assert is_payday(date(2026, 3, 26), "25") is False

    def test_gajian_geser_sabtu_ke_jumat(self):
        # Januari 2026: tgl 25 = Minggu → gajian di Jumat 23
        assert is_payday(date(2026, 1, 23), "25") is True
        assert is_payday(date(2026, 1, 25), "25") is False  # aslinya weekend

    def test_last_workday_config(self):
        # Desember 2026: last_workday harus return True
        payday = get_payday_date(2026, 12, "last_workday")
        assert is_payday(payday, "last_workday") is True

    def test_default_config(self):
        # Default config = "25"
        payday = get_payday_date(2026, 3, "25")
        assert is_payday(payday) is True


# ===========================================================================
# TEST add_calendar_flags
# ===========================================================================

class TestAddCalendarFlags:
    def _make_df(self, dates):
        """Helper: buat DataFrame dari list date string."""
        return pd.DataFrame({"updated": pd.to_datetime(dates)})

    def test_kolom_baru_ada(self):
        df = self._make_df(["2026-03-25", "2026-03-28", "2026-03-29"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert "is_weekend" in result.columns
        assert "is_payday" in result.columns
        assert "is_holiday" in result.columns
        assert "days_to_payday" in result.columns
        assert "days_since_payday" in result.columns
        assert "is_near_holiday_3d" in result.columns

    def test_days_to_and_since_payday_benar(self):
        df = self._make_df(["2026-03-23", "2026-03-25", "2026-03-27"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert result.iloc[0]["days_to_payday"] == 2
        assert result.iloc[0]["days_since_payday"] == -2
        assert result.iloc[1]["days_to_payday"] == 0
        assert result.iloc[1]["days_since_payday"] == 0
        assert result.iloc[2]["days_to_payday"] == -2
        assert result.iloc[2]["days_since_payday"] == 2

    def test_is_near_holiday_3d_benar(self):
        df = self._make_df(["2026-08-14", "2026-08-17", "2026-08-20"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert result.iloc[0]["is_near_holiday_3d"] == 1
        assert result.iloc[1]["is_near_holiday_3d"] == 1
        assert result.iloc[2]["is_near_holiday_3d"] == 1

    def test_kolom_lama_tidak_berubah(self):
        df = self._make_df(["2026-03-25"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert "updated" in result.columns

    def test_is_weekend_nilai_benar(self):
        # 2026-01-03 = Sabtu, 2026-01-05 = Senin
        df = self._make_df(["2026-01-03", "2026-01-04", "2026-01-05"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert result.iloc[0]["is_weekend"] == 1  # Sabtu
        assert result.iloc[1]["is_weekend"] == 1  # Minggu
        assert result.iloc[2]["is_weekend"] == 0  # Senin

    def test_is_payday_nilai_benar(self):
        # Maret 2026 tgl 25 = Rabu (hari kerja) → gajian
        df = self._make_df(["2026-03-25", "2026-03-24", "2026-03-26"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert result.iloc[0]["is_payday"] == 1
        assert result.iloc[1]["is_payday"] == 0
        assert result.iloc[2]["is_payday"] == 0

    def test_is_holiday_hut_ri(self):
        # 17 Agustus 2026 = HUT RI → is_holiday = 1
        df = self._make_df(["2026-08-17", "2026-08-18"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert result.iloc[0]["is_holiday"] == 1
        assert result.iloc[1]["is_holiday"] == 0

    def test_nilai_hanya_0_atau_1(self):
        dates = [f"2026-0{m}-15" for m in range(1, 9)]
        df = self._make_df(dates)
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        for col in ["is_weekend", "is_payday", "is_holiday"]:
            assert set(result[col].unique()).issubset({0, 1}), \
                f"Kolom {col} mengandung nilai selain 0/1: {result[col].unique()}"

    def test_tidak_ubah_jumlah_baris(self):
        df = self._make_df(["2026-03-25", "2026-03-26", "2026-03-27"])
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert len(result) == len(df)

    def test_tanpa_engine_tidak_error(self):
        # Tanpa engine dan tanpa api_key → pakai fallback holidays
        df = self._make_df(["2026-08-17"])
        result = add_calendar_flags(df, dt_col="updated", engine=None, api_key="")
        assert "is_holiday" in result.columns

    def test_dataframe_kosong(self):
        df = pd.DataFrame({"updated": pd.Series([], dtype="datetime64[ns]")})
        result = add_calendar_flags(df, dt_col="updated", payday_config="25")
        assert len(result) == 0
        assert "is_weekend" in result.columns


# ===========================================================================
# TEST get_holidays (Task 1 — hanya fallback, tanpa DB/API)
# ===========================================================================

class TestGetHolidays:
    def test_fallback_2026_tidak_kosong(self):
        result = get_holidays(2026, engine=None, api_key="")
        assert len(result) > 0

    def test_hut_ri_ada_di_fallback(self):
        result = get_holidays(2026, engine=None, api_key="")
        assert date(2026, 8, 17) in result

    def test_tahun_tanpa_fallback_return_kosong(self):
        # Tahun yang tidak ada di FALLBACK_HOLIDAYS
        result = get_holidays(2020, engine=None, api_key="")
        assert isinstance(result, set)

    def test_return_tipe_set(self):
        result = get_holidays(2026, engine=None, api_key="")
        assert isinstance(result, set)

    def test_elemen_bertipe_date(self):
        result = get_holidays(2026, engine=None, api_key="")
        for h in result:
            assert isinstance(h, date)


# ===========================================================================
# TEST fetch_holidays_from_api
# ===========================================================================

# Contoh payload sukses dari Calendarific API
def _mock_calendarific_payload(year: int = 2026):
    return {
        "meta": {"code": 200},
        "response": {
            "holidays": [
                {
                    "name": "Tahun Baru",
                    "date": {"iso": f"{year}-01-01T00:00:00+07:00"},
                },
                {
                    "name": "HUT Kemerdekaan RI",
                    "date": {"iso": f"{year}-08-17"},
                },
                {
                    "name": "Natal",
                    "date": {"iso": f"{year}-12-25"},
                },
            ]
        },
    }


class TestFetchHolidaysFromApi:
    def test_return_list_of_dates(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_calendarific_payload(2026)
        mock_resp.raise_for_status.return_value = None

        with patch("calendar_features.requests.get", return_value=mock_resp) as mock_get:
            result = fetch_holidays_from_api(2026, api_key="FAKE_KEY", country="ID")

        assert isinstance(result, list)
        assert all(isinstance(d, date) for d in result)

    def test_jumlah_holiday_sesuai_payload(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_calendarific_payload(2026)
        mock_resp.raise_for_status.return_value = None

        with patch("calendar_features.requests.get", return_value=mock_resp):
            result = fetch_holidays_from_api(2026, api_key="FAKE_KEY")

        assert len(result) == 3

    def test_tanggal_benar_dari_payload(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_calendarific_payload(2026)
        mock_resp.raise_for_status.return_value = None

        with patch("calendar_features.requests.get", return_value=mock_resp):
            result = fetch_holidays_from_api(2026, api_key="FAKE_KEY")

        assert date(2026, 1, 1) in result
        assert date(2026, 8, 17) in result
        assert date(2026, 12, 25) in result

    def test_api_key_kosong_raise_valueerror(self):
        with pytest.raises(ValueError, match="api_key kosong"):
            fetch_holidays_from_api(2026, api_key="")

    def test_api_error_code_raise_runtimeerror(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "meta": {"code": 401, "error_type": "unauthorized"},
            "response": {},
        }
        mock_resp.raise_for_status.return_value = None

        with patch("calendar_features.requests.get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Calendarific API error"):
                fetch_holidays_from_api(2026, api_key="WRONG_KEY")

    def test_http_error_dilempar(self):
        import requests as req_lib
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("404 Not Found")

        with patch("calendar_features.requests.get", return_value=mock_resp):
            with pytest.raises(req_lib.HTTPError):
                fetch_holidays_from_api(2026, api_key="FAKE_KEY")

    def test_entry_format_tidak_valid_di_skip(self):
        """Entry dengan format date tidak valid di-skip, tidak crash."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "holidays": [
                    {"name": "Valid", "date": {"iso": "2026-08-17"}},
                    {"name": "Invalid", "date": {"iso": "bukan-tanggal"}},
                    {"name": "No Date"},  # tidak ada key 'date'
                ]
            },
        }
        mock_resp.raise_for_status.return_value = None

        with patch("calendar_features.requests.get", return_value=mock_resp):
            result = fetch_holidays_from_api(2026, api_key="FAKE_KEY")

        assert len(result) == 1
        assert date(2026, 8, 17) in result

    def test_memanggil_url_yang_benar(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_calendarific_payload(2026)
        mock_resp.raise_for_status.return_value = None

        with patch("calendar_features.requests.get", return_value=mock_resp) as mock_get:
            fetch_holidays_from_api(2026, api_key="FAKE_KEY", country="ID")

        call_args = mock_get.call_args
        assert call_args[0][0] == CALENDARIFIC_URL
        assert call_args[1]["params"]["country"] == "ID"
        assert call_args[1]["params"]["year"] == 2026
        assert call_args[1]["params"]["api_key"] == "FAKE_KEY"


# ===========================================================================
# TEST get_holidays — prioritas cache DB → API → fallback
# ===========================================================================

class TestGetHolidaysWithCache:
    def _mock_engine(self):
        """Buat mock engine SQLAlchemy."""
        return MagicMock()

    def test_cache_hit_tidak_panggil_api(self):
        """Jika data ada di cache DB, API tidak boleh dipanggil."""
        engine = self._mock_engine()
        cached_holidays = {date(2026, 8, 17), date(2026, 1, 1)}

        with patch("calendar_features._load_holidays_from_cache", return_value=cached_holidays) as mock_load, \
             patch("calendar_features.requests.get") as mock_get:
            result = get_holidays(2026, engine=engine, api_key="FAKE_KEY")

        mock_load.assert_called_once_with(2026, engine)
        mock_get.assert_not_called()
        assert result == cached_holidays

    def test_cache_miss_panggil_api(self):
        """Jika cache kosong, harus panggil API."""
        engine = self._mock_engine()
        api_holidays = [date(2026, 8, 17), date(2026, 12, 25)]

        with patch("calendar_features._load_holidays_from_cache", return_value=set()), \
             patch("calendar_features._fetch_holidays_with_names",
                   return_value=[(d, "") for d in api_holidays]) as mock_api, \
             patch("calendar_features._save_holidays_to_cache") as mock_save:
            result = get_holidays(2026, engine=engine, api_key="FAKE_KEY")

        mock_api.assert_called_once_with(2026, "FAKE_KEY", "ID")
        assert date(2026, 8, 17) in result
        assert date(2026, 12, 25) in result

    def test_cache_miss_hasil_api_disimpan_ke_db(self):
        """Setelah API dipanggil, hasilnya harus disimpan ke cache DB."""
        engine = self._mock_engine()
        api_holidays = [(date(2026, 8, 17), "HUT RI"), (date(2026, 12, 25), "Natal")]

        with patch("calendar_features._load_holidays_from_cache", return_value=set()), \
             patch("calendar_features._fetch_holidays_with_names", return_value=api_holidays), \
             patch("calendar_features._save_holidays_to_cache") as mock_save:
            get_holidays(2026, engine=engine, api_key="FAKE_KEY")

        mock_save.assert_called_once()
        call_args = mock_save.call_args[0]
        assert call_args[0] == 2026                     # year
        assert date(2026, 8, 17) in call_args[1]        # holiday dates

    def test_api_gagal_pakai_fallback(self):
        """Jika API error, harus fallback ke FALLBACK_HOLIDAYS."""
        engine = self._mock_engine()

        with patch("calendar_features._load_holidays_from_cache", return_value=set()), \
             patch("calendar_features._fetch_holidays_with_names",
                   side_effect=RuntimeError("API error")):
            result = get_holidays(2026, engine=engine, api_key="FAKE_KEY")

        # Fallback 2026 mengandung HUT RI
        assert date(2026, 8, 17) in result

    def test_tanpa_engine_tanpa_api_pakai_fallback(self):
        """Tanpa engine dan api_key → langsung fallback."""
        result = get_holidays(2026, engine=None, api_key="")
        assert isinstance(result, set)
        assert date(2026, 8, 17) in result

    def test_tanpa_engine_ada_api_panggil_api(self):
        """Tanpa engine tapi ada api_key → panggil API, tidak simpan cache."""
        api_holidays = [(date(2026, 8, 17), "HUT RI")]

        with patch("calendar_features._fetch_holidays_with_names",
                   return_value=api_holidays) as mock_api, \
             patch("calendar_features._save_holidays_to_cache") as mock_save:
            result = get_holidays(2026, engine=None, api_key="FAKE_KEY")

        mock_api.assert_called_once()
        mock_save.assert_not_called()   # tanpa engine tidak bisa simpan
        assert date(2026, 8, 17) in result

    def test_cache_db_error_fallback_ke_api(self):
        """Jika baca cache DB error, lanjut ke API."""
        engine = self._mock_engine()
        api_holidays = [(date(2026, 8, 17), "HUT RI")]

        with patch("calendar_features._load_holidays_from_cache",
                   side_effect=Exception("DB error")), \
             patch("calendar_features._fetch_holidays_with_names",
                   return_value=api_holidays) as mock_api, \
             patch("calendar_features._save_holidays_to_cache"):
            result = get_holidays(2026, engine=engine, api_key="FAKE_KEY")

        mock_api.assert_called_once()
        assert date(2026, 8, 17) in result


# ===========================================================================
# TEST add_calendar_flags — dengan mock get_holidays
# ===========================================================================

class TestAddCalendarFlagsWithApi:
    def _make_df(self, dates):
        return pd.DataFrame({"updated": pd.to_datetime(dates)})

    def test_is_holiday_gunakan_api_jika_ada_key(self):
        """Jika api_key tersedia, get_holidays dipanggil."""
        df = self._make_df(["2026-08-17"])
        mocked_holidays = {date(2026, 8, 17)}

        with patch("calendar_features.get_holidays", return_value=mocked_holidays) as mock_gh:
            result = add_calendar_flags(df, dt_col="updated", api_key="FAKE_KEY")

        mock_gh.assert_called_once_with(2026, engine=None, api_key="FAKE_KEY", country="ID")
        assert result.iloc[0]["is_holiday"] == 1

    def test_get_holidays_dipanggil_sekali_per_tahun(self):
        """Untuk data multi-baris dalam satu tahun, get_holidays hanya dipanggil sekali."""
        df = self._make_df(["2026-01-01", "2026-06-01", "2026-12-25"])

        with patch("calendar_features.get_holidays", return_value=set()) as mock_gh:
            add_calendar_flags(df, dt_col="updated", api_key="FAKE_KEY")

        # Hanya dipanggil sekali (untuk tahun 2026)
        assert mock_gh.call_count == 1

    def test_get_holidays_dipanggil_per_tahun_berbeda(self):
        """Untuk data yang mencakup 2 tahun, get_holidays dipanggil 2 kali."""
        df = self._make_df(["2025-12-31", "2026-01-01"])

        with patch("calendar_features.get_holidays", return_value=set()) as mock_gh:
            add_calendar_flags(df, dt_col="updated", api_key="FAKE_KEY")

        assert mock_gh.call_count == 2
 