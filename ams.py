# myAMS - Shopee AMS Affiliate App (Tab 1, 2, 6 Only)
# NOTE: Helper functions & DB logic are preserved

import streamlit as st
import base64
import time
import hmac
import hashlib
import urllib.parse
import requests
import pandas as pd
import io
from supabase import create_client, Client
import datetime  # Module
from datetime import datetime as dt, timedelta, time as dt_time, date  # Class dengan alias
import time as time_module  # ✅ Import time module dengan alias
import pytz


WIB = pytz.timezone('Asia/Jakarta')
UTC = pytz.UTC

# ===============================
# PAGE CONFIG
# ===============================
st.set_page_config(page_title="myAMS - Shopee Affiliate AMS", layout="wide")

# ===============================
# SUPABASE CONFIG
# ===============================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===============================
# SHOPEE CONFIG (AFFILIATE APP)
# ===============================
PARTNER_ID = st.secrets.get("PARTNER_ID", "")
PARTNER_KEY = st.secrets.get("PARTNER_KEY", "")
REDIRECT_URL = st.secrets.get("REDIRECT_URL", "")
BASE_URL = "https://partner.shopeemobile.com"

# ===============================
# OAUTH PARAMS (AUTO-FILL SUPPORT)
# ===============================
# Gunakan st.query_params yang baru, bukan experimental
query_params = st.query_params
oauth_code = query_params.get("code", "")
oauth_shop_id = query_params.get("shop_id", "")

# Simpan ke session state agar persist ke Tab 2
if "oauth_code" not in st.session_state:
    st.session_state.oauth_code = oauth_code if oauth_code else ""
if "oauth_shop_id" not in st.session_state:
    st.session_state.oauth_shop_id = oauth_shop_id if oauth_shop_id else ""

# Update session state jika ada params baru di URL
if oauth_code:
    st.session_state.oauth_code = oauth_code
if oauth_shop_id:
    st.session_state.oauth_shop_id = oauth_shop_id

# ===============================
# SIGNATURE HELPERS
# ===============================
def generate_sign_basic(path, timestamp):
    base = f"{PARTNER_ID}{path}{timestamp}"
    return hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()

def generate_sign_full(path, timestamp, access_token, shop_id):
    base = f"{PARTNER_ID}{path}{timestamp}{access_token}{shop_id}"
    return hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()

# ===============================
# DB HELPERS (UNCHANGED)
# ===============================
def save_token_to_db(shop_name, shop_id, access_token, refresh_token):
    supabase.table("shopee_tokens").upsert({
        "shop_name": shop_name,
        "shop_id": int(shop_id),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "updated_at": "now()"
    }).execute()

def get_all_shops():
    res = supabase.table("shopee_tokens").select("shop_name").execute()
    return [r["shop_name"] for r in res.data] if res.data else []

def get_shop_token(shop_name):
    res = supabase.table("shopee_tokens").select("*").eq("shop_name", shop_name).execute()
    return res.data[0] if res.data else None

def save_report_to_db(shop_name, date_range, excel_bytes):
    supabase.table("shopee_reports").insert({
        "shop_name": shop_name,
        "date_range": date_range,
        "csv_content": base64.b64encode(excel_bytes).decode(),
        "created_at": "now()"
    }).execute()

def get_report_history(shop_name):
    res = supabase.table("shopee_reports").select("*").eq("shop_name", shop_name).order("created_at", desc=True).limit(10).execute()
    return res.data

def format_to_wib(time_str):
    """Konversi string timestamp ke format WIB"""
    if not time_str:
        return ""
    try:
        # Parse string timestamp (biasanya dari API dalam format tertentu)
        # Jika API mengembalikan UTC timestamp dalam string
        if isinstance(time_str, (int, float)):
            dt_utc = dt.fromtimestamp(time_str, UTC)  # ✅ Gunakan alias dt
            dt_wib = dt_utc.astimezone(WIB)
            return dt_wib.strftime('%Y-%m-%d %H:%M:%S')
        return str(time_str)
    except:
        return str(time_str)
    
# ===============================
# UI
# ===============================
st.title("📊 myAMS - Shopee Affiliate Conversion")

# Notifikasi otomatis jika ada code dari redirect
if st.session_state.oauth_code and st.session_state.oauth_shop_id:
    st.success(f"✅ Authorization berhasil! Code dan Shop ID otomatis terisi di Tab 2. Code: {st.session_state.oauth_code[:20]}...")

tab1, tab2, tab6 = st.tabs([
    "1️⃣ Authorisasi Affiliate",
    "2️⃣ Tukar Code → Token",
    "6️⃣ Seller Conversion (AMS)"
])

# ===============================
# TAB 1 — AUTHORISASI
# ===============================
with tab1:
    st.header("Generate Authorization URL (Affiliate App)")

    if st.button("🔐 Generate Authorization URL"):
        path = "/api/v2/shop/auth_partner"
        ts = int(time.time())
        sign = generate_sign_basic(path, ts)

        params = {
            "partner_id": PARTNER_ID,
            "timestamp": ts,
            "sign": sign,
            "redirect": REDIRECT_URL
        }

        auth_url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
        st.success("Gunakan URL ini untuk authorize Affiliate / Seller")
        st.code(auth_url)
        st.info("Setelah authorize, Anda akan di-redirect kembali ke app dengan code otomatis terisi di Tab 2.")

# ===============================
# TAB 2 — TOKEN (AUTO-FILL DARI OAUTH)
# ===============================
with tab2:
    st.header("Tukar Code ke Access Token")
    
    # Gunakan session state untuk auto-fill dari URL params
    code = st.text_input("Code", value=st.session_state.oauth_code)
    shop_id = st.text_input("Shop ID", value=st.session_state.oauth_shop_id)
    shop_name = st.text_input("Nama Toko", "MyAffiliateShop")

    # Tombol clear session jika perlu input manual
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 Tukar Token"):
            if not code or not shop_id:
                st.error("Code dan Shop ID harus diisi!")
            else:
                path = "/api/v2/auth/token/get"
                ts = int(time.time())
                sign = generate_sign_basic(path, ts)

                try:
                    res = requests.post(
                        BASE_URL + path,
                        params={"partner_id": PARTNER_ID, "timestamp": ts, "sign": sign},
                        json={"code": code, "shop_id": int(shop_id), "partner_id": int(PARTNER_ID)}
                    ).json()

                    st.json(res)

                    if "access_token" in res:
                        save_token_to_db(shop_name, shop_id, res["access_token"], res["refresh_token"])
                        st.success(f"✅ Token Affiliate berhasil disimpan untuk toko: {shop_name}")
                        # Clear session state setelah berhasil
                        st.session_state.oauth_code = ""
                        st.session_state.oauth_shop_id = ""
                    else:
                        st.error(f"Gagal mendapatkan token: {res.get('message', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col2:
        if st.button("🧹 Clear Auto-fill Data"):
            st.session_state.oauth_code = ""
            st.session_state.oauth_shop_id = ""
            st.rerun()

# ===============================
# TAB 6 — AMS CONVERSION (ALL COLUMNS)
# ===============================
with tab6:
    st.header("🔁 Seller Conversion Report (AMS v2)")
    
    shops = get_all_shops()
    if not shops:
        st.warning("Belum ada toko. Silakan authorize dan tukar token di Tab 1 & 2.")
        st.stop()
    
    selected_shop = st.selectbox("🏪 Pilih Toko", shops)
    
    # =====================================================
    # DATE RANGE SELECTOR (FLEXIBLE + TIMEZONE INDONESIA)
    # =====================================================
    st.subheader("📅 Periode Laporan")
    
    date_col1, date_col2, date_col3 = st.columns([2, 2, 1])
    
    with date_col1:
        # Preset cepat
        preset = st.selectbox(
            "Preset Cepat",
            ["Custom Range", "Hari Ini", "Kemarin", "7 Hari Terakhir", "30 Hari Terakhir", "Bulan Ini", "Bulan Lalu"],
            index=3
        )
    
    # Default values - Gunakan timezone Indonesia (WIB/UTC+7)
    now_id = dt.now(WIB)  # Gunakan WIB yang sudah didefinisikan di global
    today = now_id.date()
    
    if preset == "Hari Ini":
        start_date = today
        end_date = today
    elif preset == "Kemarin":
        start_date = today - timedelta(days=1)
        end_date = today - timedelta(days=1)
    elif preset == "7 Hari Terakhir":
        start_date = today - timedelta(days=7)
        end_date = today
    elif preset == "30 Hari Terakhir":
        start_date = today - timedelta(days=30)
        end_date = today
    elif preset == "Bulan Ini":
        start_date = today.replace(day=1)
        end_date = today
    elif preset == "Bulan Lalu":
        first_day_this_month = today.replace(day=1)
        end_date = first_day_this_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
    else:  # Custom Range
        with date_col2:
            start_date = st.date_input("Dari Tanggal", today - timedelta(days=7))
        with date_col3:
            end_date = st.date_input("Sampai Tanggal", today)
    
    # VALIDASI: End date tidak boleh lebih dari hari ini
    if end_date > today:
        st.warning(f"⚠️ Tanggal akhir ({end_date}) melebihi hari ini ({today}). Otomatis diset ke hari ini.")
        end_date = today
    
    if start_date > today:
        st.warning(f"⚠️ Tanggal mulai ({start_date}) melebihi hari ini ({today}). Otomatis diset ke hari ini.")
        start_date = today
    
    # Display selected range
    delta_days = (end_date - start_date).days + 1
    st.info(f"📆 Periode: **{start_date.strftime('%d %b %Y')}** s/d **{end_date.strftime('%d %b %Y')}** ({delta_days} hari) | 🕐 Waktu Indonesia (WIB)")
    
    # Validate range (Shopee biasanya limit 30-90 hari)
    if delta_days > 90:
        st.warning("⚠️ Rentang waktu > 90 hari mungkin akan error dari API Shopee. Pertimbangkan untuk memecah periode.")

    # TAMBAHKAN DI AWAL TAB 6 (sebelum while loop) - Dictionary mapping
    STATUS_MAPPING = {
        "Completed": "Selesai",
        "Cancelled": "Dibatalkan", 
        "To Confirm": "Belum Dibayar",
        "To Ship": "Sedang Diproses",
        "Shipping": "Dikirim",
        "To Receive": "Dikirim",
        "Unpaid": "Belum Dibayar"
    }
    
    VERIFIED_STATUS_MAPPING = {
        "Valid": "Terverifikasi",
        "Invalid": "Tidak Valid",
        "Pending": "Belum Diverifikasi",
        "Processing": "Sedang Diproses"
    }
    
    ORDER_TYPE_MAPPING = {
        "Direct Order": "Pesanan Langsung",
        "Indirect Order": "Pesanan Tidak Langsung"
    }

    CATEGORY_MAPPING = {
        "100643": "Buku & Majalah",
        "100777": "Buku Bacaan", 
        "101564": "Agama & Filsafat"
        # Tambahkan mapping lainnya sesuai kebutuhan
    }

    NOTES_MAPPING = {
        "Completed": "",
        "To Confirm": "Pesanan ini belum dibayar. Menunggu Pembeli untuk menyelesaikan pembayaran.",
        "To Ship": "Status produk ini sedang ditinjau. Komisi hanya akan dibayarkan ketika pesanan selesai.",
        "Shipping": "Pesanan sedang dikirim.",
        "Cancelled": "Pesanan dibatalkan."
    }

    CAMPAIGN_TYPE_MAPPING = {
        "Seller Open Campaign": "Komisi XTRA Produk Penjual",
        "Open Campaign": "Komisi XTRA",
        "Live Campaign": "Komisi Live"
    }
    
    # =====================================================
    # FETCH DATA
    # =====================================================
    if st.button("🚀 Tarik Data Conversion", type="primary"):
        token = get_shop_token(selected_shop)
        if not token:
            st.error("❌ Token tidak ditemukan. Silakan authorize ulang.")
            st.stop()
        
        shop_id = token["shop_id"]
        access_token = token["access_token"]
        
        # Helper: Convert date to timestamp (UTC untuk API Shopee)
        def to_ts(d, end=False):
            # Buat datetime dengan timezone WIB (Asia/Jakarta)
            if end:
                dt_obj = dt.combine(d, dt_time(23, 59, 59))  # ✅ Gunakan dt_time
            else:
                dt_obj = dt.combine(d, dt_time(0, 0, 0))     # ✅ Gunakan dt_time
            
            # Localize ke WIB kemudian convert ke UTC
            dt_wib = WIB.localize(dt_obj)
            dt_utc = dt_wib.astimezone(UTC)
            return int(dt_utc.timestamp())
        
        start_ts = to_ts(start_date)
        end_ts = to_ts(end_date, end=True)
        
        # Debug info
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        path = "/api/v2/ams/get_conversion_report"
        page_no = 1
        page_size = 100
        all_orders = []
        
        with st.spinner("Mengambil data dari Shopee API..."):
            while True:
                ts = int(time_module.time())
                sign = generate_sign_full(path, ts, access_token, shop_id)
                
                params = {
                    "partner_id": PARTNER_ID,
                    "timestamp": ts,
                    "access_token": access_token,
                    "shop_id": int(shop_id),
                    "sign": sign,
                    "page_no": page_no,
                    "page_size": page_size,
                    "place_order_time_start": start_ts,
                    "place_order_time_end": end_ts
                    # "order_status": "Completed"
                }
                
                try:
                    resp = requests.get(BASE_URL + path, params=params, timeout=30).json()
                except Exception as e:
                    st.error(f"🌐 Network Error: {str(e)}")
                    break
                
                if resp.get("error"):
                    error_msg = resp.get('message', 'Unknown error')
                    st.error(f"❌ API Error: {error_msg}")
                    if "too late" in error_msg.lower() or "has not been updated" in error_msg.lower():
                        st.info("💡 Solusi: Data untuk tanggal tersebut belum tersedia. Coba gunakan preset 'Kemarin' atau periode yang sudah lewat.")
                    st.json(resp)
                    break
                
                data = resp.get("response", {})
                orders = data.get("list", [])
                
                if not orders:
                    break
                
                all_orders.extend(orders)
                
                # Update progress
                total_estimate = data.get("total_count", page_no * page_size)
                progress = min(page_no * page_size / max(total_estimate, 1), 0.95)
                progress_bar.progress(progress)
                status_text.text(f"📄 Page {page_no} | Orders: {len(all_orders)} | Items: {sum(len(o.get('items', [])) for o in all_orders)}")
                
                if not data.get("has_more", False):
                    break
                
                page_no += 1
                time_module.sleep(0.3)
        
        progress_bar.empty()
        status_text.empty()
        
        # =====================================================
        # PROCESS DATA
        # =====================================================
        if not all_orders:
            st.warning("📭 Tidak ada data conversion untuk periode ini.")
            st.info("💡 Tips: Coba perpanjang rentang tanggal atau cek apakah ada order completed.")
            st.stop()
        
        # Flatten data dengan mapping kolom lengkap
        rows = []
        for order in all_orders:
            # Ambil data commission di level order (untuk kalkulasi)
            order_commission = order.get("total_brand_commission", 0) or 0
            order_commission_aff = order.get("total_brand_commission_to_affiliate", 0) or 0
            order_commission_mcn = order.get("total_brand_commission_to_mcn", 0) or 0
            
            items = order.get("items", [])
            item_count = len(items) if items else 1  # Hindari division by zero

            def safe_float(val):
                try:
                    return float(val) if val is not None else 0.0
                except (ValueError, TypeError):
                    return 0.0

            def safe_percent(val):
                """Safely convert percentage value to formatted string"""
                if val is None:
                    return "0%"
                try:
                    # Jika sudah string dengan %, bersihkan dulu
                    if isinstance(val, str):
                        val = val.replace('%', '').strip()
                    return f"{int(float(val))}%"
                except (ValueError, TypeError):
                    return "0%"
            
            # Hitung total komisi per order dari semua items
            # total_order_commission = sum(
            #     safe_float(i.get("item_brand_commission")) for i in items
            # )
            # total_order_commission_aff = sum(
            #     safe_float(i.get("item_brand_commission_to_affiliate")) for i in items
            # )
            # total_order_commission_mcn = sum(
            #     safe_float(i.get("item_brand_commission_to_mcn")) for i in items
            # )
            total_order_commission = sum(
                safe_float(i.get("item_brand_commission")) for i in items
            )
            total_order_commission_aff = sum(
                safe_float(i.get("item_brand_commission_to_affiliate")) for i in items
            )
            total_order_commission_mcn = sum(
                safe_float(i.get("item_brand_commission_to_mcn")) for i in items
            )
            
            # Jika total dari items 0, coba ambil dari order level
            if total_order_commission_aff == 0:
                total_order_commission_aff = safe_float(order.get("total_brand_commission_to_affiliate"))
            if total_order_commission == 0:
                total_order_commission = safe_float(order.get("total_brand_commission"))
            if total_order_commission_mcn == 0:
                total_order_commission_mcn = safe_float(order.get("total_brand_commission_to_mcn"))
            
            is_first_item = True
            
            for item in items:
                # Kalkulasi komisi per produk (rata-rata jika multiple items)
                item_commission = safe_float(item.get("item_brand_commission"))
                item_commission_aff = safe_float(item.get("item_brand_commission_to_affiliate"))
                item_commission_mcn = safe_float(item.get("item_brand_commission_to_mcn"))

                if item_commission_aff > 0:
                    pengeluaran = int(item_commission_aff * 1.11)
                else:
                    pengeluaran = 0

                if is_first_item:
                    order_commission_aff_val = total_order_commission_aff
                    order_commission_val = total_order_commission
                    order_commission_mcn_val = total_order_commission_mcn
                    is_first_item = False  # Set flag ke False untuk item berikutnya
                else:
                    order_commission_aff_val = 0
                    order_commission_val = 0
                    order_commission_mcn_val = 0
                
                # Format waktu ke WIB
                place_time = format_to_wib(order.get("place_order_time"))
                completed_time = format_to_wib(order.get("order_completed_time"))
                conv_time = format_to_wib(order.get("conversion_completed_time"))
                
                row = {
                    # === IDENTITAS PESANAN ===
                    "Kode Pesanan": order.get("order_sn"),
                    "Status Pesanan": STATUS_MAPPING.get(order.get("order_status"), order.get("order_status")),
                    "Status Terverifikasi": VERIFIED_STATUS_MAPPING.get(order.get("verified_status"), order.get("verified_status")),
                    "Waktu Pesanan": place_time,
                    "Waktu Pesanan Selesai": completed_time,
                    "Waktu Pesanan Terverifikasi": conv_time,
                    
                    # === DETAIL PRODUK ===
                    "Kode Produk": item.get("item_id"),
                    "Nama Produk": item.get("item_name"),
                    "ID Model": item.get("model_id"),
                    "L1 Kategori Global": CATEGORY_MAPPING.get(str(item.get("l1_category_id")), item.get("l1_category_id")),
                    "L2 Kategori Global": CATEGORY_MAPPING.get(str(item.get("l2_category_id")), item.get("l2_category_id")),
                    "L3 Kategori Global": CATEGORY_MAPPING.get(str(item.get("l3_category_id")), item.get("l3_category_id")),
                    
                    # === PROMO & HARGA ===
                    "Kode Promo": item.get("promotion_id"),
                    "Harga(Rp)": item.get("price", 0),
                    "Jumlah": item.get("qty", 0),
                    
                    # === AFFILIATE INFO ===
                    "Nama Affiliate": order.get("affiliate_name"),
                    "Username Affiliate": order.get("affiliate_username"),
                    "MCN Terhubung": order.get("linked_mcn"),
                    "ID Komisi Pesanan": item.get("commission_id") or order.get("commission_id") or order.get("open_id") or order.get("affiliate_id"),  # atau commission_id jika ada
                    "Partner Promo": item.get("campaign_partner"),
                    "Jenis Promo": CAMPAIGN_TYPE_MAPPING.get(item.get("seller_campaign_type"), item.get("seller_campaign_type")),
                    
                    # === FINANSIAL ===
                    "Nilai Pembelian(Rp)": item.get("purchase_value", 0),
                    "Jumlah Pengembalian(Rp)": item.get("refund_amount", 0),
                    "Tipe Pesanan": ORDER_TYPE_MAPPING.get(order.get("order_type"), order.get("order_type")),
                    
                    # === KOMISI PER PRODUK (ITEM LEVEL) ===
                    "Estimasi Komisi per Produk(Rp)": item_commission,
                    "Estimasi Komisi Affiliate per Produk(Rp)": item_commission_aff,
                    "Persentase Komisi Affiliate per Produk": safe_percent(item.get('item_brand_commission_rate_to_affiliate')),
                    "Estimasi Komisi MCN per Produk(Rp)": item_commission_mcn,
                    "Persentase Komisi MCN per Produk": safe_percent(item.get('item_brand_commission_rate_to_mcn')),
                    
                    # === KOMISI PER PESANAN (ORDER LEVEL) ===
                    "Estimasi Komisi per Pesanan(Rp)": order_commission_val,
                    "Estimasi Komisi Affiliate per Pesanan(Rp)": order_commission_aff_val,
                    "Estimasi Komisi MCN per Pesanan(Rp)": order_commission_mcn_val,
                    
                    # === LAINNYA ===
                    "Catatan Produk": NOTES_MAPPING.get(order.get("order_status"), ""),
                    "Platform": order.get("channel"),
                    "Pengeluaran(Rp)": pengeluaran,
                    "Status Pemotongan": "Menunggu Pemotongan" if order.get("verified_status") != "Valid" else "Terverifikasi",
                    "Metode Pemotongan": "" if order.get("verified_status") != "Valid" else "Otomatis",
                    "Waktu Pemotongan": "" if not conv_time or conv_time == "--" else conv_time,
                }
                rows.append(row)
        
        # Create DataFrame dengan kolom terurut sesuai permintaan
        desired_columns = [
            "Kode Pesanan", "Status Pesanan", "Status Terverifikasi", "Waktu Pesanan", 
            "Waktu Pesanan Selesai", "Waktu Pesanan Terverifikasi", "Kode Produk", 
            "Nama Produk", "ID Model", "L1 Kategori Global", "L2 Kategori Global", 
            "L3 Kategori Global", "Kode Promo", "Harga(Rp)", "Jumlah", "Nama Affiliate",
            "Username Affiliate", "MCN Terhubung", "ID Komisi Pesanan", "Partner Promo",
            "Jenis Promo", "Nilai Pembelian(Rp)", "Jumlah Pengembalian(Rp)", "Tipe Pesanan",
            "Estimasi Komisi per Produk(Rp)", "Estimasi Komisi Affiliate per Produk(Rp)",
            "Persentase Komisi Affiliate per Produk", "Estimasi Komisi MCN per Produk(Rp)",
            "Persentase Komisi MCN per Produk", "Estimasi Komisi per Pesanan(Rp)",
            "Estimasi Komisi Affiliate per Pesanan(Rp)", "Estimasi Komisi MCN per Pesanan(Rp)",
            "Catatan Produk", "Platform", "Pengeluaran(Rp)", "Status Pemotongan",
            "Metode Pemotongan", "Waktu Pemotongan"
        ]


        df = pd.DataFrame(rows)
        
        # =====================================================
        # SAFE NUMERIC CONVERSION
        # =====================================================
        numeric_cols = [
            'Harga(Rp)', 'Jumlah', 'Nilai Pembelian(Rp)', 'Jumlah Pengembalian(Rp)',
            'Estimasi Komisi per Produk(Rp)', 'Estimasi Komisi Affiliate per Produk(Rp)',
            'Persentase Komisi Affiliate per Produk', 'Estimasi Komisi MCN per Produk(Rp)',
            'Persentase Komisi MCN per Produk', 'Estimasi Komisi per Pesanan(Rp)',
            'Estimasi Komisi Affiliate per Pesanan(Rp)', 'Estimasi Komisi MCN per Pesanan(Rp)',
            'Pengeluaran(Rp)'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Reorder columns sesuai permintaan
        existing_cols = [c for c in desired_columns if c in df.columns]
        df = df[existing_cols]
        
        # =====================================================
        # DISPLAY RESULTS
        # =====================================================
        st.success(f"✅ Berhasil! {len(df)} item dari {len(all_orders)} orders")
        
        # Metrics Summary
        metric_cols = st.columns(4)
        metrics = [
            ("💰 Total Purchase", df['Nilai Pembelian(Rp)'].sum(), "Rp {:,.0f}"),
            ("💸 Total Pengeluaran", df['Pengeluaran(Rp)'].sum(), "Rp {:,.0f}"),
            ("👥 Ke Affiliate", df['Estimasi Komisi Affiliate per Produk(Rp)'].sum(), "Rp {:,.0f}"),
            ("🏢 Ke MCN", df['Estimasi Komisi MCN per Produk(Rp)'].sum(), "Rp {:,.0f}")
        ]
        
        for col, (label, value, fmt) in zip(metric_cols, metrics):
            with col:
                st.metric(label, fmt.format(value))
        
        st.dataframe(df, use_container_width=True, height=500)
        
        # =====================================================
        # EXPORT EXCEL
        # =====================================================
        st.divider()
        st.subheader("📥 Export Data")
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='AMS Conversion')
            
            # Auto-adjust
            worksheet = writer.sheets['AMS Conversion']
            for column in worksheet.columns:
                max_length = max(len(str(cell.value) or "") for cell in column) + 2
                worksheet.column_dimensions[column[0].column_letter].width = min(max_length, 50)
        
        excel_data = excel_buffer.getvalue()
        
        exp_col1, exp_col2, exp_col3 = st.columns([1, 1, 2])
        
        with exp_col1:
            st.download_button(
                label="📥 Download Excel",
                data=excel_data,
                file_name=f"AMS_{selected_shop}_{start_date}_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with exp_col2:
            if st.button("💾 Simpan ke Database"):
                try:
                    save_report_to_db(selected_shop, f"{start_date} to {end_date}", excel_data)
                    st.success("✅ Tersimpan!")
                except Exception as e:
                    st.error(f"Gagal simpan: {e}")
        
        with exp_col3:
            with st.expander("🔍 Lihat Sample Data Raw (JSON)"):
                st.json(all_orders[0] if all_orders else {})
